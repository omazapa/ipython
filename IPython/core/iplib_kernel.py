# -*- coding: utf-8 -*-
# Copyright 2010  Omar Andres Zapata Mesa
# Copyright 2010  Fernando Perez 
# Copyright 2010  Brian Granger

import __builtin__
import zmq
import sys
import time
import traceback

from IPython.utils.session import Session, Message, extract_header
from IPython.utils import session
from IPython.core.completer import KernelCompleter
from IPython.core.iplib import InteractiveShell
from IPython.core import ultratb
from IPython.core import hooks
from IPython.core.display_trap import DisplayTrap
from IPython.core.builtin_trap import BuiltinTrap
from IPython.utils.io import IOTerm

class OutStream(object):
    """A file like object that publishes the stream to a 0MQ PUB socket."""

    def __init__(self, session, pub_socket, name, max_buffer=200):
        self.session = session
        self.pub_socket = pub_socket
        self.name = name
        self._buffer = []
        self._buffer_len = 0
        self.max_buffer = max_buffer
        self.parent_header = {}

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)

    def close(self):
        self.pub_socket = None

    def flush(self):
        if self.pub_socket is None:
            raise ValueError(u'I/O operation on closed file')
        else:
            if self._buffer:
                data = ''.join(self._buffer)
                content = {u'name':self.name, u'data':data}
                msg = self.session.msg(u'stream', content=content,
                                       parent=self.parent_header)
                print>>sys.__stdout__, Message(msg)
                self.pub_socket.send_json(msg)
                self._buffer_len = 0
                self._buffer = []

    def isattr(self):
        return False

    def next(self):
        raise IOError('Read not supported on a write only stream.')

    def read(self, size=None):
        raise IOError('Read not supported on a write only stream.')

    readline=read

    def write(self, s):
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            self._buffer.append(s)
            self._buffer_len += len(s)
            self._maybe_send()

    def _maybe_send(self):
        if '\n' in self._buffer[-1]:
            self._buffer=self._buffer[0:-1]
            self.flush()
        if self._buffer_len > self.max_buffer:
            self.flush()

    def writelines(self, sequence):
        if self.pub_socket is None:
            raise ValueError('I/O operation on closed file')
        else:
            for s in sequence:
                self.write(s)


class DisplayHook(object):

    def __init__(self, session, pub_socket):
        self.session = session
        self.pub_socket = pub_socket
        self.parent_header = {}

    def __call__(self, obj):
        if obj is None:
            return

        __builtin__._ = obj
        msg = self.session.msg(u'pyout', {u'data':repr(obj)},
                               parent=self.parent_header)
        self.pub_socket.send_json(msg)

    def set_parent(self, parent):
        self.parent_header = extract_header(parent)



class InteractiveShellKernel(InteractiveShell):
    def __init__(self,session, reply_socket, pub_socket):
        self.session = session
        self.reply_socket = reply_socket
        self.pub_socket = pub_socket
        self.user_ns = {}
        self.history = []
        InteractiveShell.__init__(self,user_ns=self.user_ns,user_global_ns=self.user_ns)
        
        #getting outputs
        self.stdout = OutStream(self.session, self.pub_socket, u'stdout')
        self.stderr = OutStream(self.session, self.pub_socket, u'stderr')
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        
        self.display_hook=DisplayHook(self.session,self.pub_socket)
        #self.InteractiveTB.out_stream=self.stderr
        
        #setting our own completer
        self.completer=KernelCompleter(self,self.user_ns)
        self.handlers = {}
        for msg_type in ['execute_request', 'complete_request']:
            self.handlers[msg_type] = getattr(self, msg_type)
       
    def abort_queue(self):
        while True:
            try:
                ident = self.reply_socket.recv(zmq.NOBLOCK)
            except zmq.ZMQError, e:
                if e.errno == zmq.EAGAIN:
                    break
            else:
                assert self.reply_socket.rcvmore(), "Unexpected missing message part."
                msg = self.reply_socket.recv_json()
            print>>sys.__stdout__, "Aborting:"
            print>>sys.__stdout__, Message(msg)
            msg_type = msg['msg_type']
            reply_type = msg_type.split('_')[0] + '_reply'
            reply_msg = self.session.msg(reply_type, {'status' : 'aborted'}, msg)
            print>>sys.__stdout__, Message(reply_msg)
            self.reply_socket.send(ident,zmq.SNDMORE)
            self.reply_socket.send_json(reply_msg)
            # We need to wait a bit for requests to come in. This can probably
            # be set shorter for true asynchronous clients.
            time.sleep(0.1)

    def execute_request(self, ident, parent):
        #send messages for current user
        self.display_hook.set_parent(parent)
        
        try:
            code = parent[u'content'][u'code']
        except:
            print>>sys.__stderr__, "Got bad msg: "
            print>>sys.__stderr__, Message(parent)
            return
        
        pyin_msg = self.session.msg(u'pyin',{u'code':code}, parent=parent)
        self.pub_socket.send_json(pyin_msg)
        try:
            #this command run source but it dont raise some exception
            self.runlines(code)
            
        except (OverflowError, SyntaxError, ValueError, TypeError, MemoryError):
            result = u'error'
            etype, evalue, tb = sys.exc_info()
            tb = traceback.format_exception(etype, evalue, tb)
            exc_content = {
                u'status' : u'error',
                u'traceback' : tb,
                u'etype' : unicode(etype),
                u'evalue' : unicode(evalue)
            }
            exc_msg = self.session.msg(u'pyerr', exc_content, parent)
            self.pub_socket.send_json(exc_msg)
            reply_content = exc_content
        else:
            reply_content = {'status' : 'ok'}
        
        reply_msg = self.session.msg(u'execute_reply', reply_content, parent)

        print>>sys.__stdout__, Message(reply_msg)
        self.reply_socket.send(ident, zmq.SNDMORE)
        self.reply_socket.send_json(reply_msg)
        if reply_msg['content']['status'] == u'error':
            self.abort_queue()
            
        

    def complete_request(self, ident, parent):
        matches = {'matches' : self.complete(parent),
                   'status' : 'ok'}
        completion_msg = self.session.send(self.reply_socket, 'complete_reply',
                                           matches, parent, ident)
        print >> sys.__stdout__, completion_msg

    def complete(self, msg):
        return self.completer.complete(msg.content.line, msg.content.text)

    def start(self):
        while True:
            ident = self.reply_socket.recv()
            assert self.reply_socket.rcvmore(), "Unexpected missing message part."
            msg = self.reply_socket.recv_json()
            omsg = Message(msg)
            print>>sys.__stdout__, omsg
            handler = self.handlers.get(omsg.msg_type, None)
            if handler is None:
                print >> sys.__stderr__, "UNKNOWN MESSAGE TYPE:", omsg
            else:
                handler(ident, omsg)
         
if __name__ == "__main__" :
    c = zmq.Context(1)

    ip = '127.0.0.1'
    port_base = 5555
    connection = ('tcp://%s' % ip) + ':%i'
    rep_conn = connection % port_base
    pub_conn = connection % (port_base+1)

    print >>sys.__stdout__, "Starting the kernel..."
    print >>sys.__stdout__, "On:",rep_conn, pub_conn

    session = Session(username=u'kernel')

    reply_socket = c.socket(zmq.XREP)
    reply_socket.bind(rep_conn)

    pub_socket = c.socket(zmq.PUB)
    pub_socket.bind(pub_conn)

    #stdout = OutStream(session, pub_socket, u'stdout')
    #stderr = OutStream(session, pub_socket, u'stderr')
    #sys.stdout = stdout
    #sys.stderr = stderr
    #display_hook = DisplayHook(session, pub_socket)
    #sys.displayhook = display_hook

    kernel = InteractiveShellKernel(session, reply_socket, pub_socket)
    
    print >>sys.__stdout__, "Use Ctrl-\\ (NOT Ctrl-C!) to terminate."
    kernel.start()
