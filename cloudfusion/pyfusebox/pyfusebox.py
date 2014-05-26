from cloudfusion.store.store import NoSuchFilesytemObjectError,\
    AlreadyExistsError, StoreAccessError, StoreAutorizationError
import os, stat,  time
from errno import *
from cloudfusion.fuse import FuseOSError, Operations
import tempfile
import logging


# Specify what Fuse API use: 0.2
#fuse.fuse_python_api = (0, 2)

def zstat():
    now = time.time()
    st = {}
    st['st_mode'] = 0
    st['st_ino']  = 0
    st['st_dev']  = 0
    st['st_nlink']= 1
    st['st_uid']  = os.getuid()
    st['st_gid']  = os.getgid()
    st['st_size'] = 0
    st['st_atime']= now
    st['st_mtime']= now
    st['st_ctime']= now
    return st

class PyFuseBox(Operations):
    def __init__(self, path, store):
        self.root = path
        self.temp_file = {}
        self.read_temp_file = {}
        self.store = store
        self.logger = logging.getLogger('pyfusebox')
        self.logger.info("PyFuseBox initialized")

        #store.store_file(file, root_dir)
    def getattr(self, path, fh=None):
        #FuseOSError(EPERM)#zugriff nicht moeglich
        self.logger.debug("getattr %s", path)
        st = zstat()
        try:
            metadata = self.store.get_metadata(path)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) 
        except:
            raise FuseOSError(ENOENT)
        st['st_atime']= metadata['modified']
        st['st_mtime']= metadata['modified']
        st['st_ctime']= metadata['modified']
        if metadata['is_dir']:
            self.logger.debug(" isDir")
            st['st_mode'] = 0777 | stat.S_IFDIR
            st['st_nlink']=2
            st['st_size'] = 4096
        else:
            self.logger.debug(" isFile")
            st['st_mode'] = 0777 | stat.S_IFREG
            st['st_size'] = metadata['bytes']
        st['st_blocks'] = (int) ((st['st_size'] + 511) / 512)
        return st
    
    def open(self, path, flags):
        self.logger.debug("open %s", path)
        """self.logger.debug("open "+path+"")
        temp_file = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
        #self.temp_file = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
        if self.store.exists(path):
            file = self.store.get_file(path)
            self.temp_file.write(file)
            self.temp_file.seek(0)
        else:
            self.store.store_fileobject(self.temp_file,path)
        #self.store.store_fileobject(self.temp_file,path)
        self.store.store_fileobject(temp_file,path)"""
        return 0
    
    def truncate(self, path, length, fh=None):
        self.logger.debug("truncate %s to %s", path, length)
        if self.store.get_max_filesize() < length:
            self._release(path, 0) #to prevent flushing
            return FuseOSError(EFBIG)
        if not path in self.temp_file:
            data = ""
            self.temp_file[path] = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
            try:
                data = self.store.get_file(path)
            except NoSuchFilesytemObjectError:
                raise FuseOSError(ENOENT)
            except StoreAccessError:
                raise FuseOSError(EIO)
            except StoreAutorizationError:
                raise FuseOSError(EACCES) 
        else:
            data = self.temp_file[path].read()
        self.temp_file[path].truncate()
        self.temp_file[path].write(data[:length])
        padding = length - len(data)
        if padding > 0:
            self.temp_file[path].write('\x00'*padding)
        self.temp_file[path].seek(0)
        return 0
    
    def rmdir(self, path):
        #raise FuseOSError(EPERM)#nicht gefunden
        self.logger.debug("rmdir %s", path)
        try:
            if len(self.store.get_directory_listing(path)) > 0:
                raise FuseOSError(ENOTEMPTY) # directory not empty
            self.store.delete(path, True)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) 
        return 0
        
    def mkdir(self, path, mode):
        #raise FuseOSError(EACCES)#keine berechtigung
        #raise FuseOSError(EPERM) #operation ist nicht moeglich
        self.logger.debug("mkdir %s with mode: %s", path, mode)
        try:
            self.store.create_directory(path)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except AlreadyExistsError:
            raise FuseOSError(EEXIST)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) #keine Berechtigung
        return 0

    def statfs(self, path):
        """ This implementation should be looked at by a linux guru, since I have little experience concerning filesystems. """
        ret = {}
        ret['f_bsize'] = 4096 #Preferred file system block size.
        try:
            ret['f_bavail'] = int( self.store.get_free_space() / ret['f_bsize'] ) #Free blocks available to non-super user.
            ret['f_bfree'] = int( self.store.get_free_space() / ret['f_bsize'] ) #Total number of free blocks.
            ret['f_blocks'] = int( self.store.get_overall_space() / ret['f_bsize'] ) #Total number of blocks in the filesystem.
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) #keine Berechtigung
        ret['f_favail'] = 810280 #Free nodes available to non-super user -- not sure about this
        ret['f_ffree'] = ret['f_favail'] #Total number of free file nodes.
        ret['f_files'] = 810280 #Total number of file nodes -- not sure about this
        ret['f_flag'] = 4096 #Flags. System dependent: see statvfs() man page.
        ret['f_frsize'] = 4096 #Fundamental file system block size.
        ret['f_namemax'] = 255 #Maximum file name length.
        return ret
    
    def rename(self, old, new):
        self.logger.debug("rename %s to %s", old, new)
        try:
            try:
                source_is_file = not self.store.is_dir(old)
                destination_is_directory = self.store.is_dir(new)
                if source_is_file and destination_is_directory:
                    raise FuseOSError(EISDIR)
            except NoSuchFilesytemObjectError:
                pass # src or dst does not exist
            #if file is opened with gedit a hidden file is written and immediately renamed to the target file without flushing 
            if old in self.temp_file: 
                self.logger.debug("flushing before renaming %s", old)
                self.store.store_fileobject(self.temp_file[old], old)
            self.store.move(old, new)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES)
        return 0

    def create(self, path, mode):
        self.logger.debug("create %s with mode %s", path, mode)
        temp_file = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
        try:
            self.store.store_fileobject(temp_file, path)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except AlreadyExistsError:
            raise FuseOSError(EEXIST)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) #keine Berechtigung
        return 0
        """       self.files[path] = dict(st_mode=(S_IFREG | mode), st_nlink=1,
            st_size=0, st_ctime=time(), st_mtime=time(), st_atime=time())
        self.fd += 1
        return self.fd
    def truncate(self, path, length, fh=None):
        self.data[path] = self.data[path][:length]
        self.files[path]['st_size'] = length"""
    
    def unlink(self, path):
        self.logger.debug("unlink %s", path)
        try:
            self.store.delete(path, False)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) #keine Berechtigung

    def read(self, path, size, offset, fh):
        #self.logger.debug("read %s bytes from %s at %s - fh %s", size, path, offset, fh)
        if not path in self.read_temp_file:
            self.logger.debug("first read of %s bytes from %s at %s - fh %s", size, path, offset, fh)
            self.read_temp_file[path] = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
            try:
                data = self.store.get_file(path)
            except NoSuchFilesytemObjectError:
                raise FuseOSError(ENOENT)
            except StoreAccessError:
                raise FuseOSError(EIO)
            except StoreAutorizationError:
                raise FuseOSError(EACCES) #keine Berechtigung
            tmp_offset = 0
            chunk_size = 10*1000*1000
            while True:
                chunk = data[tmp_offset:tmp_offset+chunk_size]
                bytes_written = self.read_temp_file[path].write(chunk)
                tmp_offset += chunk_size
                if tmp_offset > len(data):
                    break
        self.read_temp_file[path].seek(offset)
        data =  self.read_temp_file[path].read(size)
        return  data

    def write(self, path, buf, offset, fh):
        #self.logger.debug("write %s ... starting with %s at %s - fh: %s", path, buf[0:10], offset, fh)
        filesize = offset+len(buf)
        if self.store.get_max_filesize() < filesize: 
            self._release(path, 0) #to prevent flushing
            return FuseOSError(EFBIG)
        if not path in self.temp_file:
            self.logger.debug("first write to %s ... starting with %s at %s - fh: %s", path, buf[0:10], offset, fh)
            self.temp_file[path] = tempfile.SpooledTemporaryFile(max_size=20*1000*1000)
            try:
                data = self.store.get_file(path)
            except NoSuchFilesytemObjectError:
                raise FuseOSError(ENOENT)
            except StoreAccessError:
                raise FuseOSError(EIO)
            except StoreAutorizationError:
                raise FuseOSError(EACCES) #keine Berechtigung
            self.temp_file[path].write(data)
        self.slow_down_if_cache_full(filesize)
        self.temp_file[path].seek(offset)
        self.temp_file[path].write(buf)
        self.temp_file[path].seek(0)
        #self.store.store_fileobject(self.temp_file[path],path)
        return len(buf)
    
    def slow_down_if_cache_full(self, filesize):
        """Reduce write speed to 10kB/s if cache has reached its hard limit"""
        try:
            if self.store.exceeds_hard_limit():
                time.sleep(filesize/1000/10)
        except AttributeError:
            pass
    
    def flush(self, path, fh):
        self.logger.debug("flush %s - fh: %s", path, fh)
        if path in self.temp_file: #after writes
            if self.store.get_free_space() < self.temp_file[path].tell():
                self._release(path, 0)
                return FuseOSError(ENOSPC)
            try:
                self.store.store_fileobject(self.temp_file[path], path)
            except NoSuchFilesytemObjectError:
                raise FuseOSError(ENOENT)
            except StoreAccessError:
                raise FuseOSError(EIO)
            except StoreAutorizationError:
                raise FuseOSError(EACCES) #keine Berechtigung
        return 0
    
    def release(self, path, fh):
        self.logger.debug("release %s - fh: %s", path, fh)
        return self._release(path, fh) #UnicodeEncodeError: 'ascii' codec can't encode character u'\xed' in position 20: ordinal not in range(128)
    
    def _release(self, path, fh): #release implementation
        if path in self.temp_file: #after writes
            self.temp_file[path].close()
            del self.temp_file[path]
        if path in self.read_temp_file:
            self.read_temp_file[path].close()
            del self.read_temp_file[path]
        return 0  
       
    def readdir(self, path, fh):
        self.logger.debug("readdir %s", path)
        try:
            directories = self.store.get_directory_listing(path)
        except NoSuchFilesytemObjectError:
            raise FuseOSError(ENOENT)
        except StoreAccessError:
            raise FuseOSError(EIO)
        except StoreAutorizationError:
            raise FuseOSError(EACCES) #keine Berechtigung
        #self.logger.debug("readdir -> "+str(directories)+"")
        file_objects = [".", ".."]
        for file_object in directories:
            if file_object != "/":
                file_object = os.path.basename(file_object.encode('utf8'))
                file_objects.append( file_object )
        return file_objects;


