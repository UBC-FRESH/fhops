# Scratch notes for coding agent

Add the following stuff to your current plan:

## Mobilization

Machine movement costs and block setup costs, based on the distance between the blocks. Mob costs incurred only if next-block-in-machine-schedule > 1 km, else the machine "walks" itself down the road at a "per meter walked" unit cost that is a per-machine parameter.

## Synthetic datasets

We need a range of synthetic datasets that my grad student can use to test in their thesis project (based on FHOPS).

Dimensions of synthetic dataset attributes that we need to sample from:
- size (number of blocks, number of days/shifts, number of landings, number of machines, number of crews, number of workers, worker-job training capabilities where the problem gets MORE complex if some workers are trained to do multiple different jobs but can only be in one place at a time and have maximum workload constraints on a daily and weekly basis)
- harvest system (include a registry of standard systems in fhops, complete with the list of machines in each system and what types of blocks they can operate on, and productivity and cost parameters [that will modulate as a function of per-block attributes like terrain and tree species and size and harvest prescripter eg. thinning versus clearcut versus variable retention, etc.]). note that harvest systems tend to IMPLY different harvesting environments (e.g., in BC, on the coast, we could use cable or heli off-road transport versus ground-based systems in the interior... see Rosalia Jaffray MASc proposal and thesis draft github repos for details)

## Machine-to-System mapping (and consequences on machine sequecing constraints in the MIP)

- Depending on the harvesting system, jobs need to be done in a different order. Jobs can only be done be specific machines, and workers trained to do that machine-job combination.
- in this context a "harvesting system" is the intersection between a sequence of jobs that needs to be done, the machine-worker combo that does each job, and (implicitly) the operating environment

## Time step and planning horizon

- targetting 12 to 16 week planning horizon for production-grade problem instances (could be shorter for testing and validation and calibration and benchmarking tasks)
- assume default working 7 days per week, but with possible user-defined "blackout dates" (which could be regular, e.g., no working on Sundays, or irregular e.g., no working for 3 days in the middle of week 7)
- need to maintain the notion of days and weeks for reporting purposes (and also to connect to "real" world calendar time definition), but the optimization problems will schedule on a PER SHIFT basis (shift is basic unit for scheduling). allow possible differnt shift length definitions inside a given problem instance (e.g., one job-machine combo scheduled on 4 hour shift basis with 6 shifts per day, or another combo scheduled with 8 hour shifts and 3 shifts per day). currently fhops time unit is only DAYS: need to fix that.

## Rosalia Jaffray MASc thesis + FHOPS

FHOPS is directly inspired by and related to (and an integral part of) Rosalia Jaffray's MASc thesis (under my supervision, as PI of the UBC FRESH lab). I have added symlinks to GitHub repo clones of the PROPOSAL and THESIS documents she is currently writing (living documents, WIP).

See `tmp/jaffray-rosalia-masc-proposal`.
See `tmp/jaffray-rosalia-masc-thesis`.

We may need to reference these documents regularly throughout the FHOPS dev rollout to make sure the two projects stay aligned.

Just to be clear FHOPS != Jaffray thesis (but the Jaffray thesis will contribute to DEFINING, and DESIGNING, and TESTING and USING fhops).

## Anticipate multi-scenario workflows

- likely use cases for FHOPS (in graduate student research project, or in practice) will require running multiple scenarios (with different parameters) on
