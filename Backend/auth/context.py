"""Request identity propagated into synchronous repository worker threads."""
from contextvars import ContextVar
from auth.models import Actor

request_actor: ContextVar[Actor | None] = ContextVar('request_actor', default=None)
accessed_resources: ContextVar[list[tuple[str,str]] | None] = ContextVar('accessed_resources',default=None)
