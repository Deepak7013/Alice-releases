# Alice v0.33 Creation & Multimodal Output

Alice now has one creation facade for text, markdown, code, flow diagrams, images, AI-agent projects, and software projects.

## Safety boundary

- Generated content is written only under `alice_workspace/artifacts` or the existing project workspace.
- Image credentials stay in environment variables and are never embedded in prompts or files.
- AI-agent/project creation continues through the existing Builder, research, security, sandbox, testing, and rollback controls.
- Knowledge and web research are inputs, not executable instructions.
- SVG diagrams are generated deterministically and remain editable as text.

## Example

```python
from alice.creation import CreationService, CreationRequest, ArtifactKind

service.create(CreationRequest(
    prompt="Explain the login flow from user to database",
    kind=ArtifactKind.DIAGRAM,
    context={"title": "Login Flow"},
))
```
