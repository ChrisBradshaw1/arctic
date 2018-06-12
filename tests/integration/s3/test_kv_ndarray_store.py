from datetime import datetime as dt, timedelta as dtd

import bson
import numpy as np
import numpy.testing as npt
import pytest
from arctic.s3._kv_ndarray_store import KeyValueNdarrayStore
from arctic.s3.generic_version_store import GenericVersionStore
from mock import patch
from pymongo.server_type import SERVER_TYPE

from arctic.s3.key_value_datastore import DictBackedKeyValueStore
from arctic.s3.generic_version_store import register_versioned_storage
from tests.integration.store.test_version_store import _query


@pytest.fixture()
def kv_store():
    store = DictBackedKeyValueStore()
    return store


@pytest.fixture
def generic_version_store(library_name, kv_store):
    register_versioned_storage(KeyValueNdarrayStore)
    return GenericVersionStore(library_name, backing_store=kv_store)


def test_save_read_simple_ndarray(generic_version_store):
    ndarr = np.ones(1000)
    generic_version_store.write('MYARR', ndarr)
    saved_arr = generic_version_store.read('MYARR').data
    assert np.all(ndarr == saved_arr)


def test_save_read_big_1darray(generic_version_store):
    ndarr = np.random.rand(5326, 6020).ravel()
    generic_version_store.write('MYARR', ndarr)
    saved_arr = generic_version_store.read('MYARR').data
    assert np.all(ndarr == saved_arr)


def test_save_and_resave_reuses_chunks(generic_version_store, kv_store):
    with patch.object(kv_store, 'chunk_size', 1000):
        ndarr = np.random.rand(1024)
        generic_version_store.write('MYARR', ndarr)
        saved_arr = generic_version_store.read('MYARR').data
        assert np.all(ndarr == saved_arr)
        orig_chunks = len(kv_store.store)
        assert orig_chunks == 9

        # Concatenate more values
        ndarr = np.concatenate([ndarr, np.random.rand(10)])
        # And change the original values - we're not a simple append
        ndarr[0] = ndarr[1] = ndarr[2] = 0
        generic_version_store.write('MYARR', ndarr)
        saved_arr = generic_version_store.read('MYARR').data
        npt.assert_almost_equal(ndarr, saved_arr)

        # Should contain the original chunks, but not double the number
        # of chunks
        new_chunks = len(kv_store.store)
        assert new_chunks == 11

        assert len(generic_version_store._backing_store.versions['MYARR']) == 2
        #assert generic_version_store._collection.find({'parent': {'$size': 2}}).count() == 7


def test_save_read_big_2darray(generic_version_store):
    ndarr = np.random.rand(5326, 6020)
    generic_version_store.write('MYARR', ndarr)
    saved_arr = generic_version_store.read('MYARR').data
    npt.assert_almost_equal(ndarr, saved_arr)


def xtest_get_info_bson_object(library):
    ndarr = np.ones(1000)
    library.write('MYARR', ndarr)
    assert library.get_info('MYARR')['handler'] == 'NdarrayStore'


def xtest_save_read_ndarray_with_array_field(library):
    ndarr = np.empty(10, dtype=[('A', 'int64'), ('B', 'float64', (2,))])
    ndarr['A'] = 1
    ndarr['B'] = 2
    library.write('MYARR', ndarr)
    saved_arr = library.read('MYARR').data


def xtest_save_read_ndarray(library):
    ndarr = np.empty(1000, dtype=[('abc', 'int64')])
    library.write('MYARR', ndarr)
    saved_arr = library.read('MYARR').data
    assert npt.assert_almost_equal(ndarr, saved_arr)


def test_multiple_write(generic_version_store):
    ndarr = np.empty(1000, dtype=[('abc', 'int64')])
    foo = np.empty(900, dtype=[('abc', 'int64')])
    generic_version_store.write('MYARR', foo)
    v1 = generic_version_store.read('MYARR').version
    generic_version_store.write('MYARR', ndarr[:900])
    v2 = generic_version_store.read('MYARR').version
#    generic_version_store.append('MYARR', ndarr[-100:])
#    v3 = generic_version_store.read('MYARR').version

    assert np.all(ndarr[:900] == generic_version_store.read('MYARR').data)
    # npt.assert_almost_equal(ndarr, generic_version_store.read('MYARR', as_of=v3).data)
    # npt.assert_almost_equal(foo, generic_version_store.read('MYARR', as_of=v1).data)
    # npt.assert_almost_equal(ndarr[:900], generic_version_store.read('MYARR', as_of=v2).data)


def xtest_cant_write_objects():
    store = NdarrayStore()
    assert not store.can_write(None, None, np.array([object()]))


def xtest_save_read_large_ndarray(library):
    dtype = np.dtype([('abc', 'int64')])
    ndarr = np.arange(30 * 1024 * 1024 / dtype.itemsize).view(dtype=dtype)
    assert len(ndarr.tostring()) > 16 * 1024 * 1024
    library.write('MYARR', ndarr)
    saved_arr = library.read('MYARR').data
    assert np.all(ndarr == saved_arr)


def xtest_mutable_ndarray(library):
    dtype = np.dtype([('abc', 'int64')])
    ndarr = np.arange(32).view(dtype=dtype)
    ndarr.setflags(write=True)
    library.write('MYARR', ndarr)
    saved_arr = library.read('MYARR').data
    assert saved_arr.flags['WRITEABLE']


@pytest.mark.xfail(reason="delete_version not safe with append...")
def xtest_delete_version_shouldnt_break_read(library):
    data = np.arange(30)
    yesterday = dt.utcnow() - dtd(days=1, seconds=1)
    _id = bson.ObjectId.from_datetime(yesterday)
    with patch("bson.ObjectId", return_value=_id):
        library.write('symbol', data, prune_previous_version=False)

    # Re-Write the data again
    library.write('symbol', data, prune_previous_version=False)
    library._delete_version('symbol', 1)
    assert repr(library.read('symbol').data) == repr(data)
