# Content origins (source map)

Where the bundled sample courses came from. The original material isn't
shipped. Paths are relative to `${SOURCE_ROOT}`, the source folder on whichever
machine you run AiTutor (see `docs/REQUIREMENTS.md`). The distilled course texts
that *are* shipped live in `aitutor/content/courses/`.

| Origin | Path (relative to `${SOURCE_ROOT}`) | Role |
| --- | --- | --- |
| AD_ASTRA pack | `${SOURCE_ROOT}/AD_ASTRA/` | Syllabi + series notes (distilled into `content/courses/`) |
| Professor prompt design | `${SOURCE_ROOT}/Grok 3 as a Professor Prompt Design - Grok.html` | Persona / tutoring style for human sessions |
| NASA Modeling course | `${SOURCE_ROOT}/NASA Modeling Course Overview - Grok.html` | Overlaps `GZsyllabus_NASA_modeling.txt` |
| Related later | other course conversation exports under `${SOURCE_ROOT}` | Add as examples when ready |

AiTutor doesn't vendor large exports or their asset folders. It points to them, distills them, and teaches from them.
