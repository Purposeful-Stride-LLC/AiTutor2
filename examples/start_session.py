"""Example: use AiTutor from another Python program.

Works from any directory once AiTutor is installed (`pip install -e .` or
`pip install .`). Bundled courses are found inside the installed package.
"""

from aitutor.nova_bridge import TutorModule

mod = TutorModule()
print("Courses:", [c["id"] for c in mod.list_courses()])

session = mod.start_session("geology-aerospace", week=1, learner_name="Alex")
print(session.last_tutor())
# Send session.prompt_bundle() to the model host of your choice.
