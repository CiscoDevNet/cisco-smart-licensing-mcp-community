"""cisco-smart-licensing-mcp: community MCP server for Cisco Smart Software Manager.

Talks to the cloud CSSM Cisco "Software APIs"
(``https://apx.cisco.com/v1/software/apis``) using an OAuth 2.0
**client-credentials** bearer token obtained from Cisco's IdP.

The interactive CSSM web UI at software.cisco.com sits behind Cisco SSO; this
server never touches that path. It authenticates machine-to-machine with a
client_id/secret registered on the Cisco API Developer Portal, so no human
login / SAML / MFA is in the request path.
"""

__version__ = "0.1.0.dev0"
