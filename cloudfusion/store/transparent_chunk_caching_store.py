from cloudfusion.store.chunk_caching_store import ChunkMultiprocessingCachingStore
from cloudfusion.store.transparent_store import TransparentStore, ExceptionStats
from cloudfusion.store.store_sync_thread import StoreSyncThread
import random, time

class TransparentChunkMultiprocessingCachingStore(ChunkMultiprocessingCachingStore, TransparentStore):
    '''
    Implements the :class:`cloudfusion.store.cache_stats.TransparentStore` interface to get statistics about a cache wrapping a store.
    '''
    def __init__(self, store, cache_expiration_time=60, cache_size_in_mb=2000, hard_cache_size_limit_in_mb=3000, cache_id=str(random.random()), max_archive_size_in_mb = 4, cache_dir='/tmp/cloudfusion'):
        """
        :param store: the store whose access should be cached 
        :param cache_expiration_time: the time in seconds until any cache entry is expired
        :param cache_size_in_mb: Approximate (soft) limit of the cache in MB.
        :param hard_cache_size_limit_in_mb: Hard limit of the cache in MB, exceeding this limit should slow down write operations.
        :param cache_id: Serves as identifier for a persistent cache instance. 
        :param max_archive_size_in_mb: the maximum size of an archive 
        :param cache_dir: Cache directory on local hard drive disk, default value is */tmp/cloudfusion*.""" 
        super( TransparentChunkMultiprocessingCachingStore, self ).__init__(store, cache_expiration_time, cache_size_in_mb, cache_id, max_archive_size_in_mb, cache_dir)
        self.hard_cache_size_limit = hard_cache_size_limit_in_mb
        self.cache_misses = 0
        self.cache_hits = 0
        self.exceptions_log = {}
    
    def get_cachesize(self):
        """:returns: the size of the cache in MB"""
        return self.entries.get_size_of_cached_data()/1000/1000
    
    def get_hard_limit(self):
        """:returns: the hard limit of the cache in MB, exceeding this limit should slow down write operations"""
        return self.hard_cache_size_limit
    
    def exceeds_hard_limit(self):
        """:returns: true if the hard limit of the cache is exceeded, which should should slow down write operations"""
        return self.entries.get_size_of_cached_data()/1000/1000 > self.get_hard_limit()
    
    def store_fileobject(self, fileobject, path):
        super( TransparentChunkMultiprocessingCachingStore, self ).store_fileobject(fileobject, path)
        if self.exceeds_hard_limit():
            name = "Cache_exceeds_hardlimit"
            desc = 'The cache exceeds the hard size limit of %s MB ' % self.get_hard_limit()
            self.exceptions_log = ExceptionStats.add_exception(Exception("Cache_exceeds_hardlimit"), self.exceptions_log, name, desc)
        
    def get_file(self, path_to_file):
        if self.entries.exists(path_to_file):
            self.logger.debug("cache hit %s"%path_to_file)
            self.cache_hits += 1
        else:
            self.logger.debug("cache miss %s"%path_to_file)
            self.cache_misses += 1
        return super( TransparentChunkMultiprocessingCachingStore, self ).get_file(path_to_file)
        
    def get_dirty_files(self):
        ret = []
        for path in self.entries.get_keys():
            if self.entries.is_dirty(path):
                ret.append(path)
        return ret

    def get_downloaded(self):
        return self.sync_thread.get_downloaded()
    
    def get_uploaded(self):
        return self.sync_thread.get_uploaded()
    
    def get_download_rate(self):
        return self.sync_thread.get_download_rate()
    
    def get_upload_rate(self):
        return self.sync_thread.get_upload_rate()
    
    def get_cache_hits(self):
        return self.cache_hits
    
    def get_cache_misses(self):
        return self.cache_misses
    
    def get_status_information(self):
        ret = "Last heartbeat was %d s ago."  % self.sync_thread.last_heartbeat()
        if self.sync_thread.last_heartbeat() > 60*15:
            ret += "Store died, trying to revive it..." 
            self.sync_thread.restart()
            ret += "Store revived successfully." 
        return ret
    
    def get_exception_stats(self):
        ret = self.sync_thread.get_exception_stats()
        ret.update(self.exceptions_log)
        return ret