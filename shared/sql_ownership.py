"""Tenant criteria and mutation checks for request-scoped ORM sessions."""
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.orm import with_loader_criteria


def restrict_session(session, policies):
    @event.listens_for(session.sync_session, "do_orm_execute")
    def restrict_reads(state):
        if state.is_select or state.is_update or state.is_delete:
            for model, field, allowed in policies:
                state.statement = state.statement.options(with_loader_criteria(model, getattr(model, field).in_(allowed), include_aliases=True))

    @event.listens_for(session.sync_session, "before_flush")
    def restrict_writes(sync_session, context, instances):
        for obj in set(sync_session.new) | set(sync_session.dirty) | set(sync_session.deleted):
            for model, field, allowed in policies:
                if isinstance(obj, model) and str(getattr(obj, field)) not in allowed:
                    raise HTTPException(404, "Recurso no encontrado")
