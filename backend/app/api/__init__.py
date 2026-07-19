"""HTTP API layer; may depend on the engine, never the reverse.

Deliberately does NOT import the router here: route modules import
application services which in turn import API schemas/errors, so an eager
package-level router import would create a circular import whenever a
service module is imported first. app.main imports app.api.router
directly.
"""
