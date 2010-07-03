# -*- coding: utf-8 -*-
"""Tests for the zmq module, where bind and connect are defined.
"""
#-----------------------------------------------------------------------------
# Module imports
#-----------------------------------------------------------------------------

# stdlib
import os
import shutil
import tempfile



# third party
import nose.tools as nt
import zmq
# our own packages
from IPython.testing import decorators as dec

#-----------------------------------------------------------------------------
# Test functions
#-----------------------------------------------------------------------------

@dec.parametric
def frontend_connect():
        ip = '127.0.0.1'
        #ip = '99.146.222.252'
        port_base = 5555
        connection = ('tcp://%s' % ip) + ':%i'
        req_conn = connection % port_base
        sub_conn = connection % (port_base+1)
        rep_conn = connection % (port_base+2)
        
        # Create initial sockets
        c = zmq.Context(1)
        request_socket = c.socket(zmq.XREQ)
        request_socket.connect(req_conn)
        
        sub_socket = c.socket(zmq.SUB)
        sub_socket.connect(sub_conn)
        sub_socket.setsockopt(zmq.SUBSCRIBE, '')
        
        reply_socket = c.socket(zmq.REP)
        reply_socket.connect(rep_conn)

@dec.parametric
def kernel_connection():
        c = zmq.Context(1)
        
        ip = '127.0.0.1'
        port_base = 5555
        connection = ('tcp://%s' % ip) + ':%i'
        rep_conn = connection % port_base
        pub_conn = connection % (port_base+1)
        req_conn = connection % (port_base+2)
        
        print >>sys.__stdout__, "Starting the kernel..."
        print >>sys.__stdout__, "On:",rep_conn, pub_conn
        
        session = Session(username=u'kernel')
        
        reply_socket = c.socket(zmq.XREP)
        reply_socket.bind(rep_conn)
        
        pub_socket = c.socket(zmq.PUB)
        pub_socket.bind(pub_conn)
        
        
        request_socket = c.socket(zmq.REQ)
        request_socket.bind(req_conn)

