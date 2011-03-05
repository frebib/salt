'''
This module contains all fo the routines needed to set up a master server, this
involves preparing the three listeners and the workers needed by the master.
'''
# Import python modules
import os
import random
import time
import threading
# Import zeromq
import zmq
# Import salt modules
import salt.utils
import salt.payload
# Import cryptogrogphy modules
from M2Crypto import RSA


class Master(object):
    '''
    The salt master server
    '''
    def __init__(self, opts):
        '''
        Create a salt master server instance
        '''
        self.opts = opts

    def start(self):
        '''
        Turn on the master server components
        '''
        reqserv = ReqServer(self.opts)
        local = LocalServer(self.opts)
        reqserv.start()
        local.start()
        while True:
            time.sleep(1)


class Publisher(threading.Thread):
    '''
    The publihing interface, a simple zeromq publisher that sends out the
    commands.
    '''
    def __init__(self, opts):
        threading.Thread.__init__(self)
        self.opts = opts
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)

    def __bind(self):
        '''
        Bind to the interface specified in the configuration file
        '''
        binder = 'tcp://' + self.opts['interface'] + ':'\
               + self.opts['publish_port']
        print binder
        self.socket.bind(binder)

    def command(self, cmd):
        '''
        Publish out a command to the minions, takes a cmd structure, one of
        those encrypted json jobs
        '''
        self.socket.send(cmd)

    def run(self):
        '''
        Start the publisher
        '''
        self.__bind()


class ReqServer(threading.Thread):
    '''
    Starts up a threaded request server, minions send results to this
    interface.
    '''
    def __init__(self, opts):
        threading.Thread.__init__(self)
        self.opts = opts
        self.num_threads = self.opts['worker_threads']
        self.context = zmq.Context(1)
        
        self.c_uri = 'tcp://' + self.opts['interface'] + ':'\
                   + self.opts['ret_port']
        self.clients = self.context.socket(zmq.XREP)

        self.workers = self.context.socket(zmq.XREQ)
        self.w_uri = 'inproc://wokers'

    def __worker(self):
        '''
        Starts up a worker thread
        '''
        socket = self.context.socket(zmq.REP)
        socket.connect(self.w_uri)

        while True:
            package = socket.recv()
            payload = salt.payload.unpackage(package)
            ret = self.payload.package(self._handle_payload(payload))
            socket.send(ret)

    def __bind(self):
        '''
        Binds the reply server
        '''
        self.clients.bind(self.c_uri)

        self.workers.bind(self.w_uri)

        for ind in range(int(self.num_threads)):
            proc = threading.Thread(target=self.__worker)
            proc.start()

        zmq.device(zmq.QUEUE, self.clients, self.workers)

    def _handle_payload(self, payload):
        '''
        The _handle_payload method is the key method used to figure out what
        needs to be done with communication to the server
        '''
        return {'aes': self._handle_aes,
                'pub': self._handle_pub,
                'clear': self._handle_clear}[payload['enc']](payload['load'])

    def _handle_clear(self, load):
        '''
        Take care of a cleartext command
        '''
        return getattr(self, load['cmd'])(load)

    def _handle_pub(self, load):
        '''
        Handle a command sent via a public key pair
        '''
        pass

    def _handle_aes(self. load):
        '''
        Handle a command sent via an aes key
        '''
        pass

    def _auth(self, load):
        '''
        Authenticate the client, use the sent public key to encrypt the aes key
        which was generated at start up
        '''
        # 1. Verify that the key we are recieving matches the stored key
        # 2. Store the key if it is not there
        # 3. make an rsa key with the pub key
        # 4. encrypt the aes key as an encrypted pickle
        # 5. package the return and return it
        pubfn = os.path.join(self.opts['pki_dir'],
                'minions',
                load['hostname'] + '.pub')
        if os.path.isfile(pubfn):
            if not open(pubfn, 'r').read() == load['pub']:
                # The keys don't authenticate, return a failure
                ret = {'enc': 'clear',
                       'load': {'ret': False}}
        else:
            open(pubfn, 'w+').write(load['pub'])
        key = RSA.load_pub_key(pubfn)
        ret = {'enc': 'pub'}
        load = {'pub_key': None,
                'token': None,
                'aes': self.opts['aes'],
                'publish_port': self.opts['publish_port']}
        ret['load'] = key.

    def run(self):
        '''
        Start up the ReqServer
        '''
        self.__bind()


class LocalServer(ReqServer):
    '''
    Create the localhost communication interface for root clients to connect
    to
    '''
    def __init__(self, opts):
        ReqServer.__init__(self, opts)
        self.num_threads = self.opts['local_threads']
        # Prep context
        self.context = zmq.Context(1)
        # Initialize Publisher
        self.publisher = Publisher(opts)
        self.publisher.start()
        # Create clients socket
        self.c_uri = 'tcp://127.0.0.1:' + self.opts['local_port']
        self.clients = self.context.socket(zmq.XREP)
        # Create workers inproc
        self.w_uri = 'inproc://locals'
        self.workers = self.context.socket(zmq.XREQ)
        # Generate communication key - make this key more awesome
        self.key = self.__prep_key()

    def __prep_key(self):
        '''
        A key needs to be placed in the filesystem with permissions 0400 so
        clients are required to run as root.
        '''
        keyfile = os.path.join(self.opts['cachedir'], 'root_key')
        key = str(random.randint(100000000000000000000000,
            999999999999999999999999))
        open(keyfile, 'w+').write(key)
        return key

    def __worker(self):
        '''
        A localserver worker needs to run some extra checks
        '''
        socket = self.context.socket(zmq.REP)
        socket.connect(self.w_uri)

        while True:
            message = socket.recv()
            if not message.has_key('key'):
                socket.send(0) # Reply false
                continue
            if not message.has_key('cmd'):
                socket.send(0) # Reply false
                continue
            if not message['key'] == self.key:
                socket.send(0) # Reply false
                continue
            cmd = salt.utils.prep_publish_cmd(message['cmd'])
            self.publisher.command(cmd)
