#!/usr/bin/env python
# -*- coding: utf-8 -*-
# encoding: utf-8
import nose.tools as nt

def test_import_zmq():  
        import zmq
    

def test_import_session():
    from IPython.zmq import session
    
def test_import_completer():
    from IPython.zmq import completer 

def test_import_kernel():
    from IPython.zmq import kernel

def test_import_frontend():
    from IPython.zmq import frontend

