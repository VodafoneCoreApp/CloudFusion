from cloudfusion.store.store import Store
from cloudfusion.util import *
import time
from cloudfusion.util.cache import Cache
from cloudfusion.util.lru_cache import LRUCache
import os.path
import logging
from copy import deepcopy
from cloudfusion.store.store_worker import GetFreeSpaceWorker

class Entry(object):
    def __init__(self):
        self.modified = None
        self.size = 0
        self.is_dir = None
        self.is_file = None
        self.listing = None
    def set_is_file(self):
        self.is_file = True
        self.is_dir = False 
        self.listing = None
    def set_is_dir(self):
        self.is_file = False 
        self.is_dir = True
        self.size = 0
    def set_modified(self, modified=None):
        if not modified:
            self.modified= time.time()
        else:
            self.modified = modified
    def add_to_listing(self, path):
        if self.listing == None:
            return
        if not path in self.listing: 
            self.listing.append(path)
    def remove_from_listing(self, path):
        if self.listing == None:
            return
        if path in self.listing: 
            self.listing.remove(path)

class MetadataCachingStore(Store):
    def __init__(self, store, cache_expiration_time=60):
        self.store = store
        self.logger = logging.getLogger(self.get_logging_handler())
        self.logger.debug("creating MetadataCachingStore object")
        self.entries = LRUCache(cache_expiration_time,2)
        self.store_metadata = Cache(cache_expiration_time)
        self.free_space_worker = GetFreeSpaceWorker(deepcopy(store), self.logger)
        self.free_space_worker.start()
    
    def _is_valid_path(self, path):
        return self.store._is_valid_path(path)
    
    def _raise_error_if_invalid_path(self, path):
        self.store._raise_error_if_invalid_path(path)
        
    def get_name(self):
        if not self.store_metadata.exists('store_name'):
            self.store_metadata.write('store_name', self.store.get_name())
        return self.store_metadata.get_value('store_name')
    
    def get_file(self, path_to_file):
        self.logger.debug("meta cache get_file %s", path_to_file)
        ret = self.store.get_file(path_to_file)
        if self.entries.exists(path_to_file) and self.entries.is_expired(path_to_file):
            self.entries.delete(path_to_file)
        if not self.entries.exists(path_to_file):
            self.entries.write(path_to_file, Entry())
        entry = self.entries.get_value(path_to_file)
        entry.set_is_file()
        try:
            entry.size = len(ret)
        except:
            self.entries.delete(path_to_file)
        self.logger.debug("meta cache returning %s", repr(ret)[:10])
        self._add_to_parent_dir_listing(path_to_file)
        return ret
    
    def _add_to_parent_dir_listing(self, path):
        parent_dir = os.path.dirname(path)
        if not self.entries.exists(parent_dir):
            self.entries.write(parent_dir, Entry())
        entry = self.entries.get_value(parent_dir)
        entry.set_is_dir()
        entry.add_to_listing(path)
        
    def _remove_from_parent_dir_listing(self, path):
        parent_dir = os.path.dirname(path)
        if self.entries.exists(parent_dir):
            entry = self.entries.get_value(parent_dir)
            entry.remove_from_listing(path)
        
    def store_file(self, path_to_file, dest_dir="/", remote_file_name = None, interrupt_event=None):
        if dest_dir == "/":
            dest_dir = ""
        if not remote_file_name:
            remote_file_name = os.path.basename(path_to_file)
        self.logger.debug("meta cache store_file %s", dest_dir + "/" + remote_file_name)
        with open(path_to_file) as fileobject:
            fileobject.seek(0,2)
            data_len = fileobject.tell()
        path = dest_dir + "/" + remote_file_name
        self.logger.debug("meta cache store_file %s", path)
        ret = self.store.store_file(path_to_file, dest_dir, remote_file_name, interrupt_event)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
        entry = self.entries.get_value(path)
        entry.set_is_file()
        entry.size = data_len
        entry.set_modified()
        self._add_to_parent_dir_listing(path)
        return ret
        
    def store_fileobject(self, fileobject, path, interrupt_event=None):
        self.logger.debug("meta cache store_fileobject %s", path)
        fileobject.seek(0,2)
        data_len = len(fileobject.tell())
        fileobject.seek(0)
        try:
            ret = self.store.store_fileobject(fileobject, path, interrupt_event)
        finally:
            fileobject.close()
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
        entry = self.entries.get_value(path)
        entry.set_is_file()
        entry.size = data_len
        entry.set_modified()
        self._add_to_parent_dir_listing(path)
        return ret
            
    def delete(self, path, is_dir): 
        self.logger.debug("meta cache delete %s", path)
        self.store.delete(path, is_dir)
        self.entries.delete(path)
        self._remove_from_parent_dir_listing(path)
          
    def account_info(self):
        if not self.store_metadata.exists('account_info'):
            self.store_metadata.write('account_info', self.store.account_info())
        return self.store_metadata.get_value('account_info')
    
    def get_free_space(self):
        return self.free_space_worker.get_free_bytes_in_remote_store()
    
    def get_overall_space(self):
        if not self.store_metadata.exists('overall_space') or self.store_metadata.is_expired('overall_space'):
            self.store_metadata.write('overall_space', self.store.get_overall_space())
        return self.store_metadata.get_value('overall_space')
    
    def get_used_space(self):
        if not self.store_metadata.exists('used_space') or self.store_metadata.is_expired('used_space'):
            self.store_metadata.write('used_space', self.store.get_used_space())
        return self.store_metadata.get_value('used_space')

    def create_directory(self, directory):
        self.logger.debug("meta cache create_directory %s", directory)
        ret = self.store.create_directory(directory)
        if self.entries.exists(directory) and self.entries.is_expired(directory):
            self.entries.delete(directory)
        if not self.entries.exists(directory):
            self.entries.write(directory, Entry())
        entry = self.entries.get_value(directory)
        entry.set_is_dir()
        entry.listing = []
        entry.set_modified()
        self._add_to_parent_dir_listing(directory)
        return ret
        
    def duplicate(self, path_to_src, path_to_dest):
        self.logger.debug("meta cache duplicate %s to %s", path_to_src, path_to_dest)
        ret = self.store.duplicate(path_to_src, path_to_dest)
        if self.entries.exists(path_to_src) and self.entries.is_expired(path_to_src):
            self.entries.delete(path_to_src)
        if self.entries.exists(path_to_src):
            entry = deepcopy(self.entries.get_value(path_to_src))
            self.entries.write(path_to_dest, entry)
        else:
            self.entries.write(path_to_dest, Entry())
        entry = self.entries.get_value(path_to_dest)
        entry.set_modified()
        self._add_to_parent_dir_listing(path_to_dest)
        self.logger.debug("duplicated %s to %s", path_to_src, path_to_dest)
        return ret
        
    def move(self, path_to_src, path_to_dest):
        self.logger.debug("meta cache move %s to %s", path_to_src, path_to_dest)
        self.store.move(path_to_src, path_to_dest)
        if self.entries.exists(path_to_dest) and self.entries.is_expired(path_to_src):
            self.entries.delete(path_to_src)
        if self.entries.exists(path_to_src):
            entry = self.entries.get_value(path_to_src)
            self.entries.write(path_to_dest, entry)
        else:
            self.entries.write(path_to_dest, Entry())
        entry = self.entries.get_value(path_to_src)
        entry.set_modified()
        self.entries.delete(path_to_src)
        self._remove_from_parent_dir_listing(path_to_src)
        self._add_to_parent_dir_listing(path_to_dest)
 
    def get_modified(self, path):
        self.logger.debug("meta cache get_modified %s", path)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if self.entries.exists(path):
            entry = self.entries.get_value(path)
            if not entry.modified == None:
                return entry.modified
        modified = self.store.get_modified(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
            entry = self.entries.get_value(path)
        entry.set_modified(modified)
        return entry.modified
    
    def get_directory_listing(self, directory):
        self.logger.debug("meta cache get_directory_listing %s", directory)
        if self.entries.exists(directory) and self.entries.is_expired(directory):
            self.entries.delete(directory)
        if self.entries.exists(directory):
            entry = self.entries.get_value(directory)
            if not entry.listing == None:
                self.logger.debug("return cached listing %s", repr(entry.listing))
                return list(entry.listing)
        listing =  self.store.get_directory_listing(directory)
        self.logger.debug("meta cache caching %s", repr(listing))
        if not self.entries.exists(directory):
            self.entries.write(directory, Entry())
            entry = self.entries.get_value(directory)
        entry.listing =  listing
        assert self.entries.get_value(directory).listing == entry.listing
        self.logger.debug("asserted %s", repr(self.entries.get_value(directory).listing))
        return list(entry.listing)
    
    def get_bytes(self, path):
        self.logger.debug("meta cache get_bytes %s", path)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if self.entries.exists(path):
            entry = self.entries.get_value(path)
            if not entry.size == None:
                return entry.size
        size = self.store.get_bytes(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
            entry = self.entries.get_value(path)
        entry.size =  size
        return entry.size
    
    def exists(self, path):
        self.logger.debug("meta cache exists %s", path)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if not self.entries.exists(path):
            if self.store.exists(path):
                self.entries.write(path, Entry())
        return self.entries.exists(path)
    
    def _get_metadata(self, path):
        self.logger.debug("meta cache _get_metadata %s", path)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if self.entries.exists(path):
            entry = self.entries.get_value(path)
            self.logger.debug("entry exists")
            if not None in [entry.is_dir, entry.modified, entry.size]:
                return {'is_dir': entry.is_dir, 'modified': entry.modified, 'bytes': entry.size}
        self.logger.debug("meta cache _get_metadata entry does not exist or is expired")
        metadata = self.store._get_metadata(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
            entry = self.entries.get_value(path)
        if metadata['is_dir']:
            entry.set_is_dir()
        else:
            entry.set_is_file()
        entry.modified = metadata['modified']
        entry.size = metadata['bytes']
        return {'is_dir': entry.is_dir, 'modified': entry.modified, 'bytes': entry.size}

    def is_dir(self, path):
        self.logger.debug("meta cache is_dir %s", path)
        if self.entries.exists(path) and self.entries.is_expired(path):
            self.entries.delete(path)
        if self.entries.exists(path):
            entry = self.entries.get_value(path)
            if not entry.is_dir == None:
                return entry.is_dir
        is_dir = self.store.is_dir(path)
        if not self.entries.exists(path):
            self.entries.write(path, Entry())
            entry = self.entries.get_value(path)
        if is_dir:
            entry.set_is_dir()
        return entry.is_dir
    
    def get_logging_handler(self):
        return self.store.get_logging_handler()
    
    def flush(self):
        self.store.flush()
        
    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            if k == 'logger':
                setattr(result, k, self.logger)
            elif k == '_logging_handler':
                setattr(result, k, self._logging_handler)
            else:
                setattr(result, k, deepcopy(v, memo))
        return result
    
    def get_max_filesize(self):
        """Return maximum number of bytes per file"""
        return self.store.get_max_filesize()
