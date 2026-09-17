# Operation Catalog — G1

| Operation ID | Version | Target | Input | Side effect | Existing implementation reused |
|---|---:|---|---|---|---|
| `project.subtitle-font-size.set` | 1 | Project | `value`: integer 16–120 | Save setting and invalidate render state | Project ORM, invalidation service |
| `project.status.get` | 1 | Project | Empty object | None | Project/job state |

The executable source of truth is `backend/app/operations/definitions.json`. Help and schema responses are generated from it. Handler keys resolve only through the code registry.
