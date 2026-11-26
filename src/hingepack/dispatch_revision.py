from .desk_revision import *  # noqa: F401,F403
from .bench_recount.revision import replan_jobs, revise_plan

replan_dispatch = replan_jobs
revise_dispatch = revise_plan
