# Public Adoption Contract Projection

These files are the public, immutable compatibility projection used by the Project Forge ChatGPT contract for existing-repository adoption.

They define the reviewed `PROJECT_ADOPTION.json` and repository operations-profile shapes required to construct an adoption proposal without depending on conversational memory. The authoritative mutation implementation remains owned by the accepted Adoption capability identified by `chatgpt/current.json`; this directory does not transfer mutation ownership to Platform.

`chatgpt/current.json` pins both the accepted Adoption revision/protocol and immutable URLs/hashes for these projected schemas.
