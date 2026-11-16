"""Deployment Kit exception types."""


class DeploymentKitError(Exception):
    """Expected fail-closed operational or configuration error."""


class CloudflarePostWriteVerificationError(DeploymentKitError):
    """Cloudflare route mutation completed but final provider verification failed."""
