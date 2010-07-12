# -*- coding: utf-8 -*-
import os
import uuid
import pprint

import zmq

class Message(object):
    """A simple message object that maps dict keys to attributes.

    A Message can be created from a dict and a dict from a Message instance
    simply by calling dict(msg_obj)."""
    
    def __init__(self, msg_dict):
        dct = self.__dict__
        for k, v in msg_dict.iteritems():
            if isinstance(v, dict):
                v = Message(v)
            dct[k] = v

    # Having this iterator lets dict(msg_obj) work out of the box.
    def __iter__(self):
        return iter(self.__dict__.iteritems())
    
    def __repr__(self):
        return repr(self.__dict__)

    def __str__(self):
        return pprint.pformat(self.__dict__)

    def __contains__(self, k):
        return k in self.__dict__

    def __getitem__(self, k):
        return self.__dict__[k]
        
        


def msg_header(msg_id, username, session):
#	"""
#	create dictionary with header content.
#	header 
#	content {
#        'msg_id' : msg_id,
#        'username' : username,
#        'session' : session
#    }
#	"""
    return {
        'msg_id' : msg_id,
        'username' : username,
        'session' : session
    }


def extract_header(msg_or_header):
    """Given a message or header, return the header."""
    if not msg_or_header:
        return {}
    try:
        # See if msg_or_header is the entire message.
        h = msg_or_header['header']
    except KeyError:
        try:
            # See if msg_or_header is just the header
            h = msg_or_header['msg_id']
        except KeyError:
            raise
        else:
            h = msg_or_header
    if not isinstance(h, dict):
        h = dict(h)
    return h


class Session(object):
#	"""
#	this class let you manage a session to asigned user, that let you manage messages too, like send, recive 
#	messages, extract messages contents and headers.
#	The user and uuid was taked from enviroment and msg_id are incrementing 1 every call
#	"""
    def __init__(self, username=os.environ.get('USER','username')):
        self.username = username
        self.session = str(uuid.uuid4())
        self.msg_id = 0

    def msg_header(self):
#		"""
#		Generate a dict header with enviroment values like a users and uuid
#		"""
        h = msg_header(self.msg_id, self.username, self.session)
        self.msg_id += 1
        return h

    def msg(self, msg_type, content=None, parent=None):
#		"""
#		Generate a dict with full message, it have
#		msg['header']
#		msg['parent_header']
#		msg['msg_type']
#		msg['content']
#		"""
        msg = {}
        msg['header'] = self.msg_header()
        msg['parent_header'] = {} if parent is None else extract_header(parent)
        msg['msg_type'] = msg_type
        msg['content'] = {} if content is None else content
        return msg

    def send(self, socket, msg_type, content=None, parent=None, ident=None):
#		"""
#		let you send a message in the assigned socket.
#		it use self.msg to create it and Message class to encapsule it.
#		the message is send encoded with json.
#		"""
        msg = self.msg(msg_type, content, parent)
        if ident is not None:
            socket.send(ident, zmq.SNDMORE)
        socket.send_json(msg)
        omsg = Message(msg)
        return omsg

    def recv(self, socket, mode=zmq.NOBLOCK):
#		"""
#		you recieve a message in the assigned socket using json. 
#		"""
        try:
            msg = socket.recv_json(mode)
        except zmq.ZMQError, e:
            if e.errno == zmq.EAGAIN:
                # We can convert EAGAIN to None as we know in this case
                # recv_json won't return None.
                return None
            else:
                raise
        return Message(msg)


