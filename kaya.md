# Kaya HPC Documentation

**University of Western Australia — High Performance Computing**

---

## Table of Contents

1. [Getting Started](#getting-started)
  - [Applying for Access](#applying-for-access)
  - [Connecting to Kaya](#connecting-to-kaya)
  - [Data Transfer](#data-transfer)
    - [Globus](#globus)
    - [RClone (IRDS)](#rclone-irds)
  - [HPC Hardware](#hpc-hardware)
  - [Modules Basics](#modules-basics)
  - [Slurm Basics](#slurm-basics)
2. [Batch Jobs](#batch-jobs)
  - [Monitoring Jobs](#monitoring-jobs)
  - [Compute Resources](#compute-resources)
  - [Scheduler](#scheduler)
  - [Batch Anatomy](#batch-anatomy)
  - [Execution](#execution)
  - [Job Steps](#job-steps)
  - [Job Status](#job-status)
3. [Software and Environments](#software-and-environments)
  - [Julia](#julia)
  - [AlphaFold3](#alphafold3)
  - [Apptainer](#apptainer)
  - [Conda](#conda)
  - [Custom Modules](#custom-modules)
  - [Jupyter Notebooks](#jupyter-notebooks)
  - [R Packages](#r-packages)
  - [RStudio](#rstudio)
  - [Gaussian](#gaussian)
  - [OnDemand](#ondemand)
  - [PyTorch](#pytorch)
4. [Troubleshooting](#troubleshooting)
  - [Bash Cheat Sheet](#bash-cheat-sheet)
  - [Move Conda](#move-conda)
  - [Quota Issues](#quota-issues)
  - [WSL Issues](#wsl-issues)
  - [Useful Links](#useful-links)
5. [About Kaya](#about-kaya)
  - [Events and Dates](#events-and-dates)
  - [What is Kaya](#what-is-kaya)
  - [Acknowledging Kaya](#acknowledging-kaya)
  - [Kaya Fine Print](#kaya-fine-print)

---

# Getting Started

New to HPC? This section covers everything you need to get started with Kaya.

**Quick Start Guide:**

- Request Access — How to get an account
- Login — Connect to Kaya
- Load Software — Using the module system
- Submit Jobs — Running your first job

**Getting Help:** If you run into issues, contact the HPC team at [hpc-admin@uwa.edu.au](mailto:hpc-admin@uwa.edu.au)

---

## Applying for Access

### How can I access Kaya?

The Kaya HPC service is free to use for research and education purposes by members of UWA. Access to Kaya is provided on a project basis. Each project requires:

- A Principal Investigator (PI), normally a senior researcher or member of the academic staff.
- A brief project description and some initial information about how long the project is expected to run and how many users are likely to need to work on the project.
- A GitHub repository and link.
- ORCIDs for all project members.
- A valid RDMP for your research project.

The Project PI and project members are then onboarded as required and added to the project.

The PI is accountable for the resources used by the project and has ultimate responsibility for data and other resources for their project on the system.

### What do I do?

Please log a ticket with the University IT Helpdesk.

The Project Description should include:

- A couple of paragraphs about the nature of the research being undertaken.
- The software expected to be used (doesn't need to be exhaustive — just the main tools).
- An estimate of the number of users and duration of the project.
- Details of any specific hardware requirements (e.g., GPUs, large memory nodes).

---

## Connecting to Kaya

You should by now have received a welcome email that provides your system userID, a temporary password and some other information such as your project name (projectid).

### How to connect

The primary method of connecting to Kaya is using the SSH command:

```bash
ssh newuser@kaya01.hpc.uwa.edu.au
```

The `ssh` command can usually be accessed from a terminal or powershell window on most systems (Windows, MacOS & Linux).

### First login — change password prompt

The password you will need to set for Kaya is separate from your Uni ID (formerly Pheme) password. However, it has the same complexity requirements (see below) and has a 6 month expiry, just like your Uni ID.

Please note that when you first log into Kaya, you will be required to change the temporary password. You will be prompted 3 times during this process.

```
Changing password for newuser.
Current Password: <--- Needs temporary password again here, not your new one.
```

Then your 'chosen' password, and again for confirmation.

### Common difficulties logging in to Kaya

Password requirements — your password must contain at least one character from each of:

- lower case characters
- upper case characters
- number
- 'special' character. e.g. `!@#$%^&`

---

## Data Transfer

Getting your data from your research data store to your HPC project.

---

### Globus

Globus is a research data management platform that makes it easy to transfer large datasets reliably and securely, including between Kaya, the UWA Research Data Store (IRDS), your desktop, and other partnering research institutions.

Unlike tools such as rclone or scp, Globus manages transfers as background tasks: you initiate a transfer, close your browser, and Globus handles reliability, retries, and notification on completion. This makes it suited for large or long-running transfers.

Globus is operated and supported by the HPC team at UWA.

#### Before you begin

Globus accesses your storage on your behalf through mapped collections, thus you must request access before you can transfer data to or from a given storage location.

There are two collections relevant to most Kaya users:


| Storage                        | Request via                                |
| ------------------------------ | ------------------------------------------ |
| UWA Research Data Store (IRDS) | Create a mapped collection for IRDS        |
| HPC project storage            | Create a mapped collection for HPC project |


Both requests are submitted through the UWA ServiceNow portal. Once your request is processed, the HPC team will notify you when your collection is ready.

---

### RClone (IRDS)

This guide provides instructions for transferring data between IRDS and Kaya, the High-Performance Computing (HPC) cluster using Rclone.

Rclone is a command-line tool for managing files on remote file systems. The HPC team recommend the use of Rclone since it allows for file synchronisation with checksums, provides support for encryption and compression, allows for resumption of interrupted transfers, and facilitates logging and monitoring of transfer progress.

#### Initial Setup

Configure a remote connection to IRDS. Run the interactive configuration wizard:

```bash
rclone config
```

**Choose 'n' for new remote:**

```
No remotes found, make a new one?
n) New remote
s) Set configuration password
q) Quit config
n/s/q> n
```

**Enter a name for the remote:**

```
Enter name for new remote.
name> IRDS
```

**Select the storage type from the list** — the option required for IRDS is `SMB / CIFS`:

```
\ (smb)
```

**Enter the hostname:**

```
Option host.
SMB server hostname to connect to.
E.g. "example.com".
Enter a value.
host> drive.irds.uwa.edu.au
```

Enter your username and password when prompted.

---

## HPC Hardware

### Login Node

Using ssh to access Kaya via the login node (`kaya.hpc.uwa.edu.au`). The login node is the machine that you use to interact with the HPC storage and compute. From the login node all the shared filesystems are visible to the HPC.

The Kaya login node is actually a virtual machine and intentionally quite small, with only a few CPU cores and relatively little memory. **The login node must not be used to run actual work.** Applications found running on the login node will be killed.

The login node is a limited shared resource and running interactive jobs on the login node will:

- Cause the login node to run really slowly which affects everyone logged in to the system.
- The HPC team will kill any jobs found running on the login node.
- Users who repeatedly run jobs on the login node will have their access revoked.

The login node is also used to transfer data to/from Kaya, that can be done with `scp` or `sftp`.

### Compute Nodes

Kaya includes a number of general purpose compute nodes that are available to all Kaya users. Compute nodes are accessed through the Slurm job scheduler. Jobs are submitted to a queue and when resources become available, they are dispatched to the compute nodes.

---

## Modules Basics

### Module Files

The HPC system uses environment modules to provide access to system tools (compilers etc) as well as application versions, thus simplifying the shell initialisation and allowing users to dynamically modify their environment using modulefiles. Environment modules allow multiple versions of tools and applications to exist on the system and be selected at will.

**Basic Module Files Commands:**


| Command                       | Description                                         |
| ----------------------------- | --------------------------------------------------- |
| `module avail`                | Show available modules                              |
| `module list`                 | Show modules currently loaded in your environment   |
| `module add/load app/ver`     | Load environment modules for version `ver` of `app` |
| `module rm/unload app/ver`    | Unload an application module                        |
| `module show/display app/ver` | Display information about modulefile                |


To find out more about environment modules on Kaya:

```bash
module help   # get help on the module command
```

### Using application modules

In most cases, it is necessary to load a compiler module before loading the application module. If you try to load an application module and get an error about dependencies, load the compiler/prerequisite module first, then load the application module.

---

## Slurm Basics

### Slurm

Access to the compute nodes in the HPC is controlled by the system resource manager, Slurm.

The Slurm system is a batch job submission system. Jobs are submitted to a queue and when compute resources become available, the next job is taken from the queue and executed on a compute node.

This system ensures that available compute resources are used fairly and efficiently. Fairly because jobs are run on a first come, first served basis and efficiently because the queueing system tries to keep machines in the cluster busy where possible.

### Job Scripts

The basic unit of work in the HPC system is a job script. A job script is a shell script that performs a number of important steps:

1. It defines the resources required by the job e.g. number of cores and/or RAM required.
2. It sets up the environment for the application code to run.
3. Sets up data required for the job.
4. Executes the application/code.
5. Cleans up input data, saves output files etc.

Multiple jobs can be submitted and they will be queued and then allocated resources as they become available.

---

# Batch Jobs

Learn how to submit batch jobs, request resources, and monitor your computations on Kaya.

### Job Submission

Slurm is a combined batch scheduler and resource manager that allows users to run their jobs on Kaya, UWA's high performance computing (HPC) cluster. This document describes the process for submitting and running jobs under the Slurm Workload Manager.

---

## Monitoring Jobs

### Basic job monitoring

After submitting your job with `sbatch`, note the `jobid`:

```bash
squeue -j JOBID           # check queue status
scontrol show job JOBID   # detailed job info
watch squeue -j JOBID     # watch job status live
```

If finished, check accounting:

```bash
sacct -j JOBID --format=JobID,JobName,State,ExitCode,Elapsed,Start,End
```

Check output log:

```bash
ls -lh slurm-JOBID.out
tail -f slurm-JOBID.out
```

### Monitoring jobs with sacct

The `sacct` command queries the SLURM accounting database to retrieve information about past and current jobs.

### 1. Listing Your Jobs

#### 1.1 Get all your job IDs since a specific date

To retrieve a list of all jobs you have run since a given date, use the flag with your username:

```bash
sacct -S 2020-01-01 -u $USER
```

The variable `$USER` is filled in automatically with your username. Change the date (`YYYY-MM-DD` format) to narrow the results.

```bash
sacct -S $(date -d '30 days ago' +%Y-%m-%d) -u $USER
```

#### 1.2 Filter by date range

Use `-S` (start) and `-E` (end) together to see jobs from a specific window:

```bash
sacct -S 2024-01-01 -E 2024-12-31 -u $USER
```

> 💡 The default output shows: JobID, JobName, Partition, Account, AllocCPUS, State, and ExitCode.

### 2. Checking Memory and Resource Usage for a Job

Once you have a job ID, use `sacct -j <jobID>` with the `--format` flag to see detailed resource information:

```bash
sacct -j <jobID> --format=JobID,User,JobName,Start,Partition,TimeLimit,Elapsed,AllocCPUS,ReqMem,MaxRSS
```

Replace `<jobID>` with your actual job number, for example:

```bash
sacct -j 1234567 --format=JobID,User,JobName,Start,Partition,TimeLimit,Elapsed,AllocCPUS,ReqMem,MaxRSS
```

#### 2.1 What each field means


| Field     | Example             | Description                                   |
| --------- | ------------------- | --------------------------------------------- |
| JobID     | 1234567             | Unique job identifier assigned by SLURM       |
| User      | jsmith              | Username who submitted the job                |
| JobName   | my_analysis         | Name given to the job (set with `--job-name`) |
| Start     | 2024-03-01T09:00:00 | Date and time the job started running         |
| Partition | compute             | Queue/partition the job ran on                |
| TimeLimit | 02:00:00            | Maximum walltime that was requested           |
| Elapsed   | 01:23:45            | Actual time the job ran for                   |
| AllocCPUS |                     | Number of CPU cores allocated to the job      |
| ReqMem    | 16Gn                | Memory requested (n = per node, c = per core) |
| MaxRSS    | 12400000K           | Peak memory actually used by the job (in KB)  |


#### 2.2 Understanding MaxRSS — peak memory used

`MaxRSS` is an important field for memory diagnostics. It shows the peak memory your job actually consumed.

```bash
# Converting MaxRSS to GB:
# MaxRSS of 12400000K
# 12400000 / 1024 = 12109 MB
# 12400000 / 1024 / 1024 = 11.8 GB (peak memory used)
```

> ⚠️ Compare against your `ReqMem`. If `MaxRSS` is close to or over your requested memory, your job risks being killed.

### 3. Understanding Job States

The `State` column shows how a job ended. The most common states are:


| State         | Meaning                                                                 |
| ------------- | ----------------------------------------------------------------------- |
| COMPLETED     | Job finished successfully (exit code 0)                                 |
| FAILED        | Job exited with a non-zero code; check your application logs for errors |
| CANCELLED     | Job was cancelled by you (`scancel`) or by an administrator             |
| TIMEOUT       | Job exceeded its requested time limit and was killed by SLURM           |
| OUT_OF_MEMORY | Job exceeded its memory request and was killed — increase `ReqMem`      |
| PENDING       | Job is waiting in the queue and has not yet started                     |
| RUNNING       | Job is currently executing                                              |


### 4. Cancelling your job

```bash
scancel -u <username>
```

To cancel all pending jobs for a user:

```bash
scancel -t PENDING -u <username>
```

### 5. Quick Refs


| Task                           | Command                                                                                                  |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- |
| List all my jobs since a date  | `sacct -S 2020-01-01 -u $USER`                                                                           |
| List jobs in a date range      | `sacct -S 2024-01-01 -E 2024-12-31 -u $USER`                                                             |
| Check memory & stats for a job | `sacct -j <jobID> --format=JobID,User,JobName,Start,Partition,TimeLimit,Elapsed,AllocCPUS,ReqMem,MaxRSS` |


---

## Compute Resources

An HPC cluster is made up of a number of compute nodes, each with a complement of processors, memory and GPUs. The user submits jobs that specify the application(s) they want to run along with a description of the computing resources needed to run the application(s).

The processing units on nodes are the cores. The processing elements are generically called a CPU. Kaya does not implement multi-threading, therefore a CPU is a core or hardware thread.

---

## Scheduler

### The Slurm Batch Scheduler and Resource Manager

The batch scheduler and resource manager work together to run jobs on an HPC cluster. The batch scheduler, sometimes called a workload or resource manager, is responsible for finding and allocating the resources that fulfill the job's request at the soonest available time. When a job is scheduled to run, the scheduler instructs the resource manager to launch the application(s) across the job's allocated resources. This is also known as "running the job".

The user can specify conditions for scheduling the job. One condition is the completion (successful or unsuccessful) of an earlier submitted job. Other conditions include the availability of a specific license or access to a specific file system.

---

## Batch Anatomy

The `sbatch` command is used to submit a batch script to Slurm. It is designed to reject the job at submission time if there are requests or constraints that Slurm cannot fulfill as specified. This gives the user the opportunity to examine the job request and resubmit it with the necessary corrections.

A batch job requests computing resources and specifies the application(s) to launch on those resources along with any input data/options and output directives.

The batch job script is composed of six main components:

1. `#!/bin/bash` (also called a shebang), which makes the submission script a Linux bash script.
2. The interpreter used to execute the script.
3. `#SBATCH` directives that convey default submission options.
4. The setting of environment and/or script variables (if necessary).
5. Modules to load (if necessary).
6. The application(s) to execute along with its input arguments and options.

### Script flow

```
SLURM directives    → Resources, partition, time, output paths
Environment setup   → Modules, software, variables
Define paths        → Executable, scratch, results
Validate inputs     → Check files exist before starting
Prepare scratch     → Create directories, copy files
Run application     → Execute and capture exit code
Save results        → Copy from scratch to permanent storage
Clean up            → Remove scratch, report status
```

### Basic example

A minimal CPU job. Replace the placeholder values with your own paths and executable.

```bash
#!/bin/bash --login
#############################################
# SLURM directives
#SBATCH --job-name=my_job
#SBATCH --partition=work
#SBATCH --time=01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

echo "Job started at: $(date)"
echo "Job ID: $SLURM_JOBID"
echo "Node: $SLURM_NODELIST"

#############################################
# Load modules
module load <module_name>

#############################################
# Define paths
EXECUTABLE=$SLURM_SUBMIT_DIR/<your_script>
SCRATCH=$MYSCRATCH/$SLURM_JOB_NAME/$SLURM_JOBID
RESULTS=$SLURM_SUBMIT_DIR/results/$SLURM_JOBID

#############################################
# Validate inputs
if [ ! -f $EXECUTABLE ]; then
    echo "ERROR: $EXECUTABLE not found"
    exit 1
fi

#############################################
# Set up scratch
mkdir -p $SCRATCH $RESULTS
cp $EXECUTABLE $SCRATCH
cd $SCRATCH

#############################################
# Run
<your_command>
EXIT_CODE=$?
echo "Finished at: $(date) — exit code: $EXIT_CODE"

#############################################
# Copy results to permanent storage
cp -r $SCRATCH/* $RESULTS

#############################################
# Clean up scratch
rm -rf $SCRATCH
cd $HOME
echo "Results saved to: $RESULTS"
[ -ne $EXIT_CODE ] && exit $EXIT_CODE
```

Submit with:

```bash
mkdir -p logs
sbatch my_job.sh
```

> **Note:** The `logs/` directory must exist before submission — SLURM will not create it automatically.

### GPU example

Adapt this template for GPU workloads. Requires the `gpu` partition and at least one GPU resource.

```bash
#!/bin/bash --login
#############################################
# SLURM directives
#SBATCH --job-name=my_gpu_job
#SBATCH --partition=gpu
#SBATCH --time=01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err

echo "Job started at: $(date)"
echo "Job ID: $SLURM_JOBID"
echo "Node: $SLURM_NODELIST"

#############################################
# Load modules
module load <cuda_module>
module load <other_modules>

# Activate environment (if using conda)
# conda activate /path/to/your/env

#############################################
# Define paths
EXECUTABLE=$SLURM_SUBMIT_DIR/<your_script>
SCRATCH=$MYSCRATCH/$SLURM_JOB_NAME/$SLURM_JOBID
RESULTS=$SLURM_SUBMIT_DIR/results/$SLURM_JOBID

#############################################
# Validate inputs
if [ ! -f $EXECUTABLE ]; then
    echo "ERROR: $EXECUTABLE not found"
    exit 1
fi

#############################################
# Set up scratch
mkdir -p $SCRATCH $RESULTS
cp $EXECUTABLE $SCRATCH
cd $SCRATCH

#############################################
# Verify GPU
nvidia-smi

#############################################
# Run
echo "Starting at: $(date)"
<your_command>
EXIT_CODE=$?
echo "Finished at: $(date) — exit code: $EXIT_CODE"

#############################################
# Copy results to permanent storage
cp -r $SCRATCH/* $RESULTS
echo "Results saved to: $RESULTS"

#############################################
# Clean up scratch
rm -rf $SCRATCH
cd $HOME
[ -ne $EXIT_CODE ] && exit $EXIT_CODE
```

> **Note:** `--gres=gpu:1` requests one GPU. Adjust the count and type as needed for your job — check available GPU resources with `sinfo -o "%n %G"`.

### Parameters

`--partition=<partition_names>`  
Request a specific partition for the resource allocation. Each partition has its own limits for time, nodes, and memory.

`--ntasks=<number>`  
Maximum number of tasks to be invoked. The default is one task per node.

`--mem=<size[units]>`  
Specify the real memory required per node. Default units are MB (default: 1GB).

> **Important:** The job is killed if it exceeds the memory limit. Use the variable `$SLURM_MEM_PER_NODE` in your script to keep software within the memory limit.

`--time=<time>`  
Set a limit on the total run time of the job allocation. Acceptable formats: `minutes`, `minutes:seconds`, `hours:minutes:seconds`, `days-hours`, `days-hours:minutes`, `days-hours:minutes:seconds`.

---

## Execution

### Execution Environment

For each job type, the user has the ability to define the execution environment. `sbatch` and `salloc` provide the `--export` option to convey specific environment variables to the execution environment. `sbatch` and `salloc` provide the `--propagate` option to convey specific shell limits to the execution environment.

### Environment Variables

Slurm recognizes and provides a number of environment variables.

The first category of environment variables are those that Slurm inserts into the job's execution environment. These convey to the job script and application information such as job ID (`SLURM_JOB_ID`) and task ID (`SLURM_PROCID`). For the complete list, see the "OUTPUT ENVIRONMENT VARIABLES" section under the `sbatch`, `salloc`, and `srun` man pages.

The next category of environment variables are those the user can set in their environment to convey default options for every job they submit. These include options such as the wall clock limit. For the complete list, see the "INPUT ENVIRONMENT VARIABLES" section under the `sbatch`, `salloc`, and `srun` man pages.

---

## Job Steps

### Jobs and Job Steps

The job requests computing resources and when it runs, the scheduler selects and allocates those resources to the job. The invocation of the application happens within the batch script, or at the command line for interactive and xterm jobs.

When an application is launched using `srun`, it is called a "job step". The `srun` command causes the simultaneous launching of multiple tasks of a single application. Arguments to `srun` specify the number of tasks to launch as well as the number of nodes (and CPUs and memory) on which to launch the tasks.

`srun` can be invoked sequentially or in parallel (by backgrounding them). Furthermore, the number of nodes specified by `srun` (the `-N` option) can be less than but no more than the number of nodes (and CPUs and memory) that was allocated to the job.

`srun` can also be invoked directly at the command line (outside of a job allocation). Doing so will submit a job to the batch scheduler and `srun` will block until that job is scheduled to run.

---

## Job Status

Most of a job's specifications can be seen by invoking `scontrol show job jobid`. More details about the job including the job script can be seen by adding the `-d` flag. A user is unable to see the script of the job of another user.

Slurm captures and reports the exit code of the job script (`sbatch` jobs) as well as the signal that caused the job's termination when a signal caused a job's termination.

A job's record remains in Slurm's memory for 5 minutes after it completes. `scontrol show job` will return "Invalid job id specified" for a job that completed more than 5 minutes ago. At that point, one must invoke the `sacct` command to retrieve the job's record from the Slurm database.

```bash
scontrol show -dd jobid=<jobid>
```

### Job Information

`squeue` is the main command for monitoring the state of systems, groups of jobs or individual jobs. Read all the options for `squeue` on the Linux manual using the command `man squeue`, including how to personalise the information to be displayed.

---

# Software and Environments

Software guides and environment setup for HPC users.

---

## Julia

### Running Julia

#### Adding the IJulia package

Open a UNIX shell and login to Kaya. Run these commands:

```bash
module load julia/1.10.0
julia
```

```julia
using Pkg
Pkg.add("IJulia")
```

#### Opening a Jupyter Notebook with the Julia kernel on Kaya

1. Open a browser and go to [https://ondemand2.hpc.uwa.edu.au](https://ondemand2.hpc.uwa.edu.au)
2. Go to **Interactive Apps → Kaya GPU-OnDemand** (The GPU-OnDemand requirement is a temporary workaround for a problem with the current Julia version. This will be removed in a future release.)
3. Start a session with the specs required for your Jupyter notebooks session. Please be aware you cannot keep this running forever; the maximum session time is 8 hours. However, you can always go back to your notebook in a new session later.
4. Click **Launch** at the bottom of the form.
5. In **My Interactive Sessions**, wait for the **Launch Kaya OnDemand** button to appear. You may need to refresh the page. It will take a couple of minutes to get onto the node and be ready to launch.
6. Click on the magnifying glass (Application finder) at the bottom of the interactive desktop and search for Jupyter. Choose **Jupyter Notebook**.

---

## AlphaFold3

### AlphaFold3 on Kaya

AlphaFold3 can be run on Kaya using the container provided by Google DeepMind. Before proceeding, read the AlphaFold3 Terms of Use carefully — the terms for version 3 are significantly more restrictive than version 2, and the model weights are not provided as a system-wide module for this reason.

### Prerequisites

- You must obtain access to the AlphaFold3 model weights by applying via the Google DeepMind request form.
- Once approved, download the weights to your group storage.
- Ensure `$MYSOFTWARE` is set up. See the Apptainer guide for setup instructions.

### Pull the container

```bash
mkdir -p $MYSOFTWARE/alphafold3/latest
cd $MYSOFTWARE/alphafold3/latest

apptainer pull docker://google-deepmind/alphafold3
```

> **Note:** Check the AlphaFold3 repository for the current recommended container image tag before pulling.

### Run AlphaFold3

AlphaFold3 requires paths to the model weights and databases to be bound into the container at runtime. A typical run looks like:

```bash
apptainer exec \
    --bind /group/<project>/alphafold3/weights:/weights \
    --bind /group/<project>/alphafold3/databases:/databases \
    $MYSOFTWARE/alphafold3/latest/alphafold3.sif \
    python run_alphafold.py \
    --input_dir /input \
    --output_dir /output \
    --model_dir /weights \
    --db_dir /databases
```

---

## Apptainer

### Apptainer on Kaya

This guide explains how to use Apptainer on Kaya to install software containers and expose them as loadable modules. The examples use Nextflow to demonstrate the full workflow.

Before adding containers, decide whether the software is for your personal use only, or whether other members of your project also require access. Shared installs mean everyone uses the same version without each person maintaining their own copy.

- Section 1: setting up Apptainer for shared access by a project group
- Section 2: setting up Apptainer for a single researcher
- Section 3 onwards: module paths, building containers, and creating module files (same for both cases)

### Storage on Kaya


| Variable      | Path                   | Purpose                                                         |
| ------------- | ---------------------- | --------------------------------------------------------------- |
| `$MYGROUP`    | `/group/project/user`  | Your personal subdirectory within the project                   |
| (no variable) | `/group/project`       | The shared project directory, accessible to all project members |
| `$MYSOFTWARE` | set by you (see below) | Points to your chosen software install location                 |


### 1. Apptainers for a Project Group

Use this section if the software needs to be accessible to all members of your project. The container is stored in `/group/project` and the module path is set in a shared location.

### 2. Apptainer for a Single Researcher

Use this section for personal-use software. The container is stored in `$MYGROUP` and only you need to add the module path to your environment.

---

## Conda

Conda is a package manager that makes it easy to install and manage software and their dependencies without requiring administrator privileges. This guide covers installing Conda environments in shared group storage, configuring your setup, and running jobs through SLURM.

> ⚠️ **Home Directory Quota:** Your `/home` directory has a limited quota of 20 GB. Do not install conda environments there. All conda environments must be stored under `/group` storage (see below).

### Understanding Your Storage

Before setting up Conda, it is important to understand the storage layout and key environment variables:


| Variable      | Path                  | Purpose                                                                                                            |
| ------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `$MYGROUP`    | `/group/project/user` | Your personal subdirectory within the project. Use for your own data and results.                                  |
| (no variable) | `/group/project`      | The shared project directory. Recommended location for conda environments if all team members need to access them. |
| `$MYSCRATCH`  | `/scratch/user`       | Fast temporary storage for running jobs. Always clean up after each job.                                           |


### Deciding where to install Conda

- **Shared team project:** Install in `/group/project/` so all members can use the same environment.
- **Personal use:** Install in `$MYGROUP` for environments only you need.

---

## Custom Modules

### Creating Custom Modules on Kaya

This guide covers how to create Lua module files that expose software (including Apptainer containers) as loadable modules on Kaya.

**Prerequisites:** Before creating a module file, ensure you have set up your `$MYSOFTWARE` directory and added it to `$MODULEPATH`. See the Apptainer on Kaya guide for setup instructions.

### Module file location

Module files must be saved under your modulefiles directory, following this structure:

```
$MYSOFTWARE/modulefiles/<software_name>/<version>.lua
```

For example:

```
$MYSOFTWARE/modulefiles/nextflow/25.10.0.lua
```

The full path would look like:

```
/group/project001/mysoftware/modulefiles/nextflow/25.10.0.lua
```

### Writing a module file

The following Lua module file sets up the Nextflow container as a loadable module. Save it as `25.10.0.lua`:

```lua
help([[
An apptainer for running Nextflow 25.10.0
]])

whatis("Version: 25.10.0")
whatis("Keywords: System, Tool")
whatis("URL: https://www.nextflow.io/docs/latest/install.html")
whatis("Description: Running Nextflow 25.10.0 via Apptainer")

local container = pathJoin(os.getenv("MYSOFTWARE"), "nextflow/25.10.0/nextflow_25.10.0.sif")

set_shell_function("nextflow", 
    "apptainer exec " .. container .. " nextflow \"$@\"",
    "apptainer exec " .. container .. " nextflow $*"
)
```

---

## Jupyter Notebooks

### Running Jupyter Notebooks on Kaya

1. Open a browser and go to [https://ondemand2.hpc.uwa.edu.au](https://ondemand2.hpc.uwa.edu.au)
2. Go to **Interactive Apps → Kaya OnDemand**.
3. Start a session with the specs required for your Jupyter notebooks session. Please be aware you cannot keep this running forever; the maximum session time is 8 hours. However, you can always go back to your notebook in a new session later.
4. Click **Launch** at the bottom of the form.
5. In **My Interactive Sessions**, wait for the **Launch Kaya OnDemand** button to appear. You may need to refresh the page. It will take a couple of minutes to get the node and be ready to launch.
6. Click on the magnifying glass (Application finder) at the bottom of the interactive desktop and search for Jupyter. Choose **Jupyter Notebook**.
7. You should see a browser window open with your Jupyter session already loaded in the active tab.
8. Now save the notebook so that you can find it again later.

---

## R Packages

On Kaya, R packages cannot be installed into the system library. Instead, each user installs packages into a personal library stored in their project group directory.

Your personal R library is only accessible to you. If you use more than one version of R, each version requires its own library directory.

### 1. Helper Scripts and Resources

The following resources are available in the shared directory `/home/shared/Using_R/`:


| Resource                 | Location                                                             | Description                              |
| ------------------------ | -------------------------------------------------------------------- | ---------------------------------------- |
| Install script template  | `/home/shared/Using_R/R-pkg-tools/environ-setup/tidyverse-install.R` | Example install script to copy and adapt |
| SLURM job script example | `/home/shared/Using_R/job1run.slurm`                                 | Example SLURM script for running R jobs  |


> Always copy scripts to your own directory before editing — do not modify the originals in the shared directory.

### 2. Setting Up Your Library Directory

Create a directory for your R library inside your group project space. It is good practice to include the R version in the path:

```bash
mkdir -p /group/<project>/<username>/Rlibrary/<R_version>
# Example:
mkdir -p /group/ms008/mmccoy/Rlibrary/4.4.0
```

To check which versions of R are available on Kaya:

```bash
module avail R
```

### 3. Creating an Install Script

#### 3.1 Copy the template

Copy the provided example script to your home directory:

```bash
cp /home/shared/Using_R/R-pkg-tools/environ-setup/tidyverse-install.R ~/<your-package>-install.R
# i.e.:
cp /home/shared/Using_R/R-pkg-tools/environ-setup/tidyverse-install.R ~/ggplot2-install.R
```

#### 3.2 What the template contains

The template (`tidyverse-install.R`) is structured as follows:

```r
R_LIBRARY <- "/group/ms008/mmccoy/Rlibrary/4.4.0"
options(Ncpus = 12)
local({
  r <- getOption("repos")
  r["CRAN"] <- "https://mirror.aarnet.edu.au/pub/CRAN/"
  options(repos = r)
})
setRepositories(ind = 1:6)
install.packages("tidyverse", lib = "/group/ms008/mmccoy/Rlibrary/4.4.0")
```

- `R_LIBRARY` — sets the path to your personal library directory
- `options(Ncpus = 12)` — uses 12 CPU cores to speed up package compilation
- `local({...})` — sets the CRAN mirror to AARNet (Australian mirror, recommended on Kaya)
- `setRepositories(..., ind=1:6)` — enables CRAN, Bioconductor, and other repositories
- `install.packages(..., lib=...)` — installs the package into your personal library

#### 3.3 Customise for your package and project

Edit your copied script, replacing the project path, username, R version, and package name:

```r
# Update these two lines:
R_LIBRARY <- "/group/<project>/<username>/Rlibrary/<R_version>"
install.packages("<package>", lib = "/group/<project>/<username>/Rlibrary/<R_version>")

# Example for ggplot2:
R_LIBRARY <- "/group/sae020/jsmith/Rlibrary/4.4.0"
install.packages("ggplot2", lib = "/group/sae020/jsmith/Rlibrary/4.4.0")
```

Make a separate install script for each package you need.

### 4. Running an Install Script

Load the appropriate R module and run your script:

```bash
module load R/<version>
Rscript ~/<your-package>-install.R
# Example:
module load R/4.4.0
Rscript ~/ggplot2-install.R
```

> Ensure the version of R you load matches the version in your library path. Mixing versions can cause issues.

### 5. Running R Jobs on Kaya

For running R analyses as SLURM jobs, refer to the example job script provided:

```bash
/home/shared/Using_R/job1run.slurm
```

Copy it to your working directory and adapt it:

```bash
cp /home/shared/Using_R/job1run.slurm ~/myjob.slurm
```

> Do not run R analyses on the login node. Always submit compute work via SLURM.

### 6. Quick Refs


| Task                       | Command                                                                    |
| -------------------------- | -------------------------------------------------------------------------- |
| Check available R versions | `module avail R`                                                           |
| Load R                     | `module load R/<version>`                                                  |
| Copy install template      | `cp /home/shared/Using_R/R-pkg-tools/environ-setup/tidyverse-install.R ~/` |
| Create library directory   | `mkdir -p /group/<project>/<username>/Rlibrary/<R_version>`                |
| Run an install script      | `Rscript ~/<your-package>-install.R`                                       |
| Copy SLURM job example     | `cp /home/shared/Using_R/job1run.slurm ~/myjob.slurm`                      |


---

## RStudio

### Running RStudio on Kaya

1. Open a browser and go to [https://ondemand2.hpc.uwa.edu.au](https://ondemand2.hpc.uwa.edu.au)
2. Log in to OnDemand with your Kaya credentials.
3. Go to **Interactive Apps → Kaya OnDemand**.
4. Start a session with the specs required for your RStudio session. Please be aware you cannot keep this running forever; the maximum session time is 8 hours. However, you can always go back to your RStudio in a new session later.
5. Click **Launch** at the bottom of the form.
6. In **My Interactive Sessions**, wait for the **Launch Kaya OnDemand** button to appear. You may need to refresh the page. It will take a couple of minutes to get the node and be ready to launch.
7. Click on the terminal icon at the bottom of the desktop.
8. Type into the terminal:

```bash
module load r/4.0.5
module load rstudio/2023.12.1
rstudio
```

Your RStudio session should open on the OnDemand desktop.

---

## Gaussian

### Running Gaussian

```bash
module load gaussian/g16-brdwl
```

There are 2 versions of Gaussian 16 on Kaya.

- The version `gaussian/g16-brdwl` will run on all the machines currently in the cluster.
- The version `gaussian/g16` is compiled for a newer CPU architecture so is slightly better optimised for later generation CPUs. However it will not run at all on older CPUs.

If in doubt, please use the `g16-brdwl` version.

---

## OnDemand

### Running OnDemand

#### Opening an interactive GUI desktop on Kaya

1. Open a browser and go to [https://ondemand2.hpc.uwa.edu.au](https://ondemand2.hpc.uwa.edu.au)
2. Go to **Interactive Apps → Kaya OnDemand**.
3. Start a session with the specs required for your interactive session. Please be aware you cannot keep this running forever; the maximum session time is 8 hours.
  - **Walltime** — however many hours you require for this session (max 8 for most queues)
  - **Account** — should be your project ID
  - **Number of cores** — 4 is a good starting point, can specify more if you know your code will use more cores
  - **Memory** — Choose an appropriate memory size for your session. 8 or 16 GB is fine for basic web applications; request more if you will be working with large datasets.
4. Fill in your email address and check the "I would like to receive an email" box if required. For small sessions that are allocated to a machine fairly quickly, this is not normally required. However, if you are requesting a very large session that might take longer before being dispatched to a machine, it can be useful to receive an email notification when the session is ready.
5. Click **Launch**.
6. In **My Interactive Sessions**, wait for the **Launch Kaya OnDemand** button to appear. It will take a couple of minutes.
7. Click **Launch Kaya OnDemand** to open the interactive desktop in your browser.

---

## PyTorch

This guide covers how to set up a conda environment with PyTorch and submit GPU jobs on Kaya.

### Available GPU Hardware


| GPU Model          | Nodes                | GPUs per node | VRAM           | Partition             |
| ------------------ | -------------------- | ------------- | -------------- | --------------------- |
| NVIDIA Tesla V100  | k026–k044 (18 nodes) | 2             | 16 GB or 32 GB | `gpu`, `ondemand-gpu` |
| AMD Instinct MI210 | k014–k015 (2 nodes)  | 2             | 64 GB          | `amdgpu`              |


This guide focuses on NVIDIA V100 GPUs. For AMD GPU usage, see the [AMD GPUs (ROCm)](#amd-gpus-rocm) section.

### Storage Paths


| Variable     | Path                      | Purpose                                                            |
| ------------ | ------------------------- | ------------------------------------------------------------------ |
| `$MYGROUP`   | `/group/GROUPNAME/USER`   | Permanent project storage — use for code, environments and results |
| `$MYSCRATCH` | `/scratch/GROUPNAME/USER` | Fast temporary storage — use during jobs, clean up afterwards      |


> **Important:** Your home directory (`/home/USER`) is capped at 20 GB and cannot be increased. Do not install conda environments there.

### Prerequisites — Initialise Conda

Before using conda for the first time on Kaya, run the following once to initialise your shell:

```bash
module load Anaconda3/2024.06
conda init bash
source ~/.bashrc
```

This adds conda to your shell configuration. You only need to do this once.

### Setting Up a PyTorch Environment

#### Step 1 — Load modules

```bash
module load Anaconda3/2024.06
module load cuda/12.6.3
```

#### Step 2 — Create a conda environment in your group storage

Use `--prefix` to install into your group storage rather than your home directory. Alternatively, configure `~/.condarc` ([see below](#configuring-condarc)).

```bash
conda create --prefix $MYGROUP/envs/pytorch_env python=3.11
conda activate $MYGROUP/envs/pytorch_env
```

#### Step 3 — Install PyTorch

Use `pip` rather than `conda` to install PyTorch on Kaya. Installing via conda has been found to cause MKL library conflicts.

```bash
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124
```

The `cu124` build is compatible with the `cuda/12.6.3` driver on Kaya.

#### Step 4 — Install additional packages

```bash
conda install matplotlib -c conda-forge
pip install numpy scipy pandas
```

#### Step 5 — Verify the installation

Run this on the login node to confirm packages are available:

```bash
python -c "import torch; print(torch.__version__)"
```

> **Note:** `torch.cuda.is_available()` will return `False` on the login node as there is no GPU present. GPU detection can only be verified inside a job — see [Verifying GPU Access](#verifying-gpu-access).

#### Step 6 — Export your environment for reproducibility

```bash
conda env export > $MYGROUP/envs/environment.yml
```

To recreate the environment later:

```bash
conda env create -f $MYGROUP/envs/environment.yml \
    --prefix $MYGROUP/envs/pytorch_env
```

### Configuring ~/.condarc

If you regularly create conda environments, editing `~/.condarc` once means you can use `-n myenv` instead of `--prefix /full/path/` every time.

```yaml
envs_dirs:
  - /group/GROUPNAME/USER/envs

pkgs_dirs:
  - /group/GROUPNAME/USER/pkgs
```

Replace `GROUPNAME` and `USER` with your actual group and username. If `~/.condarc` already exists, add to it rather than replacing it.

After editing, create environments normally:

```bash
conda create -n pytorch_env python=3.11
conda activate pytorch_env
```

> **NB:** `pkgs_dirs` redirects conda's package download cache away from your home directory. This is important since the home directory has a 20 GB quota.

### Submitting a GPU Job

#### Directory structure

Organise your project as follows:

```
$MYGROUP/myproject/
├── scripts/
│   ├── train.py
│   └── submit_gpu.sh
└── results/     ← must exist before submitting
```

Create the results directory before submitting:

```bash
mkdir -p $MYGROUP/myproject/results
```

#### Example SLURM job script

```bash
#!/bin/bash --login
#SBATCH --job-name=pytorch_job
#SBATCH --partition=gpu
#SBATCH --time=08:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --output=results/job_%j.out
#SBATCH --error=results/job_%j.err

echo "Job started at: $(date)"
echo "Job ID: $SLURM_JOBID"
echo "Node: $SLURM_NODELIST"

#############################################
# Load modules and activate environment
module load Anaconda3/2024.06
module load cuda/12.6.3
conda activate $MYGROUP/envs/pytorch_env

echo "Python path: $(which python)"
echo "CUDA available: $(python -c 'import torch; print(torch.cuda.is_available())')"

#############################################
# Define paths
# Submit this script from $MYGROUP/myproject/scripts/
EXECUTABLE=$SLURM_SUBMIT_DIR/train.py
SCRATCH=$MYSCRATCH/pytorch_job/$SLURM_JOBID
RESULTS=$SLURM_SUBMIT_DIR/results/$SLURM_JOBID

echo "Scratch directory: $SCRATCH"
echo "Results directory: $RESULTS"

#############################################
# Verify input files
if [ ! -f $EXECUTABLE ]; then
    echo "ERROR: $EXECUTABLE not found"
    exit 1
fi

#############################################
# Create directories
mkdir -p $SCRATCH
mkdir -p $RESULTS

#############################################
# Copy files to scratch and run from there
cp $EXECUTABLE $SCRATCH
cd $SCRATCH

nvidia-smi

#############################################
# Run
echo "Starting job at: $(date)"
unset LD_PRELOAD
export RESULTS=$RESULTS
python train.py
EXIT_CODE=$?

echo "Job finished at: $(date)"
echo "Exit code: $EXIT_CODE"

#############################################
# Copy results back
cp -r * $RESULTS
ls -lh $RESULTS

#############################################
# Clean up scratch
echo "Cleaning up scratch: $SCRATCH"
rm -rf $SCRATCH
echo "Scratch cleaned."

cd $HOME
echo "Results saved to: $RESULTS"

if [ $EXIT_CODE -eq 0 ]; then
    echo "Job completed successfully!"
else
    echo "Job failed with exit code: $EXIT_CODE"
    exit $EXIT_CODE
fi
```

#### Submitting the job

Always submit from your scripts directory:

```bash
cd $MYGROUP/myproject/scripts
sbatch submit_gpu.sh
```

#### Checking job status

```bash
# Your jobs
squeue -u $USER

# GPU partition status
sinfo -p gpu,ondemand-gpu -o "%20P %5D %14F %10G %N"

# Watch job output as it runs
tail -f results/job_JOBID.out
```

### Verifying GPU Access

Include these lines in your job script to confirm the GPU is visible and PyTorch can use it:

```bash
nvidia-smi
python -c "import torch; print('CUDA available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0))"
```

These run on the compute node where the GPU is present. They will not work on the login node.

### GPU Partitions


| Partition      | Nodes     | Max Time | Use Case                 |
| -------------- | --------- | -------- | ------------------------ |
| `gpu`          | k026–k043 | 72 hours | Standard production jobs |
| `ondemand-gpu` | k026–k039 | 12 hours | Short test jobs          |
| `amdgpu`       | k014–k015 | 72 hours | AMD / ROCm workloads     |


No special permission is required to access these partitions.

Use `ondemand-gpu` for short test runs to avoid waiting in the queue behind longer jobs.

### Requesting Multiple GPUs

To request 2 GPUs on a single node:

```bash
#SBATCH --gres=gpu:2
```

Most nodes have 2 GPUs. For multi-node GPU jobs contact HPC support.

### Scratch Storage — Best Practice

- Always run computations from `$MYSCRATCH`, not from `$MYGROUP`.
- Copy inputs to scratch at the start of your job.
- Copy results back to `$MYGROUP` before the job ends.
- Clean up scratch at the end of every job.
- Scratch is purged after 21 days regardless — do not rely on this for results you need.

### AMD GPUs (ROCm)

ROCm is available system-wide on AMD GPU nodes — no module load required. To install PyTorch with ROCm:

```bash
conda create --prefix $MYGROUP/envs/pytorch_rocm python=3.11
conda activate $MYGROUP/envs/pytorch_rocm
pip install torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/rocm6.1
```

Submit to the `amdgpu` partition and use `rocm-smi` in place of `nvidia-smi` in your job script.

### Troubleshooting

#### `torch.cuda.is_available()` returns False

- Confirm `#SBATCH --gres=gpu:1` is in your job script.
- Confirm `#SBATCH --partition=gpu` is set.
- Run `module list` inside the job to confirm cuda is loaded.
- Check `nvidia-smi` output in your job log.

#### CUDA out of memory

- Reduce batch size.
- Add `torch.cuda.empty_cache()` between runs.
- Request 2 GPUs and split the workload.
- Use gradient accumulation to simulate larger batches.

#### Job stuck in queue (PD status)

- Check available nodes: `sinfo -p gpu`
- Use `ondemand-gpu` for short jobs.
- Check your priority: `sprio -u $USER`

#### Module conflict or import error

- Run `module purge`, then reload in order: Anaconda first, then cuda.
- Deactivate and reactivate the conda environment.
- Use `pip` to install PyTorch.
- If you see an MKL-related error, add `unset LD_PRELOAD` before your python call in the job script.

#### Job output and error files are your first resource

```bash
cat results/job_JOBID.out
cat results/job_JOBID.err
```

### Getting Help

When contacting HPC support, include:

- Job ID
- Error messages from your `.out` and `.err` files
- Your job script
- What you expected vs what happened

Contact: [hpc-admin@uwa.edu.au](mailto:hpc-admin@uwa.edu.au)

### Further Reading

- [SLURM GPU documentation](https://slurm.schedmd.com/gres.html)
- [NVIDIA CUDA documentation](https://docs.nvidia.com/cuda/)
- [PyTorch documentation](https://pytorch.org/docs/)
- [AMD ROCm documentation](https://rocmdocs.amd.com/)

---

# Troubleshooting

Please request support for the HPC system via the University IT Helpdesk portal. Ensure to include "Please forward to the HPC Team" near the start of your request so it reaches us promptly.

---

## Bash Cheat Sheet

### Command History

```bash
touch foo.sh
chmod +x !$   # !$ is the last argument of the last command i.e. foo.sh
```

### Navigating Directories

```bash
pwd                  # Print current directory path
ls                   # List directories
ls -a                # List directories including hidden
ls -l                # List directories in long form
ls -l -h             # List directories in long form with human readable sizes
ls -t                # List directories by modification time, newest first
stat foo.txt         # List size, created and modified timestamps for a file
stat foo             # List size, created and modified timestamps for a directory
tree                 # List directory and file tree
tree -a              # List directory and file tree including hidden
tree -d              # List directory tree
cd foo               # Go to foo sub-directory
cd                   # Go to home directory
cd ~                 # Go to home directory
cd -                 # Go to last directory
pushd foo            # Go to foo sub-directory and add previous directory to stack
popd                 # Go back to directory in stack saved by pushd
```

### Creating Directories

```bash
mkdir foo                    # Create a directory
mkdir foo bar                # Create multiple directories
mkdir -p foo/bar             # Create nested directory
mkdir -p foo{,bar}/baz       # Create multiple nested directories
```

### Moving Directories

```bash
cp -R foo bar                        # Copy directory
mv foo bar                           # Move directory
rsync -z -v /foo /bar                # Copy directory, overwrites destination
rsync -a -z -v /foo /bar             # Copy directory, without overwriting destination
rsync -avz /foo username@hostname:/bar   # Copy local directory to remote directory
rsync -avz username@hostname:/foo /bar   # Copy remote directory to local directory
```

### Deleting Directories

```bash
rmdir foo            # Delete empty directory foo
rm -r foo            # Delete directory including contents
rm -r -f foo         # Delete directory including contents, ignore nonexistent files and never prompt
```

### Creating Files

```bash
touch foo.txt            # Create file or update existing files modified timestamp
touch foo.txt bar.txt    # Create multiple files
touch foo{,bar}.txt      # Create multiple files
touch test{1..3}         # Create test1, test2 and test3 files
touch test{a..c}         # Create testa, testb and testc files
```

### Standard Output, Standard Error and Standard Input

```bash
echo "foo" > bar.txt         # Overwrite file with content
echo "foo" >> bar.txt        # Append to file with content
ls exists 1> stdout.txt      # Redirect the standard output to a file
ls noexist 2> stderror.txt   # Redirect the standard error output to a file
ls 2>&1 > out.txt            # Redirect standard output and error to a file
ls > /dev/null               # Discard standard output and error
read foo                     # Read from standard input and write to the variable foo
```

### Moving Files

```bash
cp foo.txt bar.txt   # Copy file
mv foo.txt bar.txt   # Move file
```

### Deleting Files

```bash
rm foo.txt           # Delete file
rm -f foo.txt        # Delete file, ignore nonexistent files and never prompt
```

### Reading Files

```bash
cat foo.txt          # Print all contents
less foo.txt         # Print some contents at a time (g - go to top of file, SHIFT+g go to bottom, /foo to search)
head foo.txt         # Print top 10 lines of file
tail foo.txt         # Print bottom 10 lines of file
open foo.txt         # Open file in the default editor
wc foo.txt           # List number of lines words and characters in the file
```

### File Permissions


| Permission              | rwx | Binary |
| ----------------------- | --- | ------ |
| read, write and execute | rwx | 111    |
| read and write          | rw- | 110    |
| read and execute        | r-x | 101    |
| read only               | r-- | 100    |
| write and execute       | -wx | 011    |
| write only              | -w- | 010    |
| execute only            | --x | 001    |
| none                    | --- | 000    |


For a directory, execute means you can enter (`cd` to) a directory.

- `u` - User
- `g` - Group
- `o` - Others
- `a` - All of the above

```bash
ls -l /foo.sh                    # List file permissions
chmod +100 foo.sh                # Add 1 to the user permission
chmod -100 foo.sh                # Subtract 1 from the user permission
chmod u+x foo.sh                 # Give the user execute permission
chmod g+x foo.sh                 # Give the group execute permission
chmod u-x,g-x foo.sh             # Take away the user and group execute permission
chmod u+x,g+x,o+x foo.sh        # Give everybody execute permission
chmod a+x foo.sh                 # Give everybody execute permission
chmod +x foo.sh                  # Give everybody execute permission
```

### Finding Files

```bash
type wget                        # Find the binary
which wget                       # Find the binary
whereis wget                     # Find the binary, source, and manual page files
```

`locate` uses an index and is fast:

```bash
updatedb                         # Update the index
locate foo.txt                   # Find a file
locate --ignore-case             # Find a file and ignore case
locate f*.txt                    # Find a text file starting with 'f'
```

`find` doesn't use an index and is slow:

```bash
find /path -name foo.txt         # Find a file
find /path -iname foo.txt        # Find a file with case insensitive search
find /path -name "*.txt"         # Find all text files
find /path -name foo.txt -delete # Find a file and delete it
find /path -name "*.png" -exec pngquant {}  # Find all .png files and execute pngquant on it
find /path -type f -name foo.txt # Find a file
find /path -type d -name foo     # Find a directory
find /path -type l -name foo.txt # Find a symbolic link
find /path -type f -mtime +30    # Find files that haven't been modified in 30 days
find /path -type f -mtime +30 -delete  # Delete files that haven't been modified in 30 days
```

### Find in Files

```bash
grep 'foo' bar.txt               # Search for 'foo' in file 'bar.txt'
grep 'foo' /bar -r               # Search for 'foo' in directory 'bar'
grep 'foo' /bar -R               # Search for 'foo' in directory 'bar' and follow symbolic links
grep 'foo' *.txt -l              # Show only files that match
grep 'foo' *.txt -L              # Show only files that don't match
grep 'Foo' bar.txt -i            # Case insensitive search
grep 'foo' bar.txt -x            # Match the entire line
grep 'foo' bar.txt -C 2          # Add N lines of context above and below each search result
grep 'foo' bar.txt -v            # Show only lines that don't match
grep 'foo' bar.txt -c            # Count the number of lines that match
grep 'foo' bar.txt -n            # Add line numbers
grep 'foo' bar.txt --colour      # Add colour to output
grep 'foo\|bar' /baz -R         # Search for 'foo' or 'bar' in directory 'baz'
grep -E 'foo|bar' /baz -R       # Use regular expressions
egrep 'foo|bar' /baz -R         # Use regular expressions
```

### Replace in Files

```bash
sed 's/fox/bear/g' foo.txt       # Replace fox with bear in foo.txt and output to console
sed 's/fox/bear/gi' foo.txt      # Replace fox (case insensitive) with bear and output to console
sed 's/red fox/blue bear/g' foo.txt  # Replace red fox with blue bear and output to console
sed 's/fox/bear/g' foo.txt > bar.txt  # Replace fox with bear and save in bar.txt
sed -i 's/fox/bear/g' foo.txt    # Replace fox with bear and overwrite foo.txt
```

### Symbolic Links

```bash
ln -s foo bar                    # Create a link 'bar' to the 'foo' folder
ln -s -f foo bar                 # Overwrite an existing symbolic link 'bar'
ls -l                            # Show where symbolic links are pointing
```

### File Compression

`gzip` and `pigz` are file compression tools. `gzip` is more widely available but `pigz` is faster. Both tools use the same options.

#### gzip

```bash
gzip bar.txt foo.gz              # Compress bar.txt into foo.gz then delete bar.txt
gzip -k /bar.txt foo.gz          # Compress bar.txt into foo.gz, keep bar.txt
gzip -d foo.gz                   # Uncompress foo.gz file to foo, deleting foo.gz file
gzip -kd foo.gz                  # Uncompress foo.gz file to foo, keep foo.gz file
```

#### pigz

```bash
pigz bar.txt foo.gz              # Compress bar.txt into foo.gz and then delete bar.txt
pigz -k /bar.txt foo.gz          # Compress bar.txt into foo.gz, keep bar.txt
pigz -d foo.gz                   # Uncompress foo.gz file to foo, deleting foo.gz file
pigz -kd foo.gz                  # Uncompress foo.gz file to foo, keep foo.gz file
```

`pigz` compresses using parallel threads so is much faster than `gzip` for compression operations. Uncompression speed is similar.

### File Archiving

#### tar

Combines one or more files into a single `*.tar` file, with optional compression.

**Create tar archives:**

```bash
tar -czf foo.tgz bar.txt baz.txt         # Compress bar.txt and baz.txt into foo.tgz
tar -czf foo.tgz /bar                     # Compress directory bar into foo.tgz
tar -cf foo.tar bar.txt bar.dir          # Write foo.tar archive containing bar.txt and bar.dir
tar -czf foo.tgz bar.txt bar.dir         # Write compressed foo.tgz containing bar.txt and bar.dir
```

**Unpack tar archives:**

```bash
tar -xzf foo.tgz                         # Uncompress foo.tgz archive file
tar -xf foo.tar                          # Unpack foo.tar archive
tar -xzf foo.tgz                         # Unpack compressed foo.tgz
```

**Other tar archive operations:**

```bash
tar -tf foo.tar                          # List contents of archive file foo.tar
tar -df foo.tar bar.txt baz.txt         # Compare contents of archive file with bar.txt & baz.txt
```

#### zip

Archives and compresses one or more files/directories into `*.zip` files.

```bash
zip foo.zip bar.txt                      # Compress bar.txt into foo.zip
zip foo.zip bar.txt baz.txt             # Compress bar.txt and baz.txt into foo.zip
zip foo.zip bar{,baz}.txt              # Compress bar.txt and baz.txt into foo.zip
zip -r foo.zip dir                      # Compress directory dir into foo.zip
unzip foo.zip                           # Unpack contents of foo.zip
```

### Disk Usage

```bash
df                               # List disks, size, used and available space
df -h                            # List disks, size, used and available space in human readable format
du                               # List current directory, subdirectories and file sizes
du /foo/bar                      # List specified directory, subdirectories and file sizes
du -h                            # List in human readable format
du -d 2                          # List within the max depth
du .                             # List current directory size
du --apparent-size               # List apparent size rather than device usage
```

Example — print sizes of top 10 largest files & directories:

```bash
du -sch --apparent-size * .??* | sort -rh | head
```

### Memory Usage

```bash
free                             # Show memory usage
free -h                          # Show human readable memory usage
free -h --si                     # Show human readable memory usage in power of 1000 instead of 1024
free -s 5                        # Show memory usage and update continuously every five seconds
```

### Identifying Processes

```bash
top                              # List all processes interactively
htop                             # List all processes interactively
ps all                           # List all processes
pidof foo                        # Return the PID of all foo processes
CTRL+Z                           # Suspend a process running in the foreground
bg                               # Resume a suspended process and run in the background
fg                               # Bring the last background process to the foreground
fg PID                           # Bring the background process with the PID to the foreground
sleep 30 &                       # Sleep for 30 seconds and move the process into the background
jobs                             # List all background jobs
jobs -l                          # List all background jobs with their PID
lsof                             # List all open files and the process using them
lsof -itcp:4000                  # Return the process listening on port 4000
```

### Killing Processes

```bash
CTRL+C                           # Kill a process running in the foreground
kill PID                         # Shut down process by PID gracefully. Sends TERM signal.
kill -9 PID                      # Force shut down of process by PID. Sends SIGKILL signal.
pkill foo                        # Shut down process by name gracefully. Sends TERM signal.
pkill -9 foo                     # Force shut down process by name. Sends SIGKILL signal.
killall foo                      # Kill all processes with the specified name gracefully.
```

### Date & Time

```bash
date                             # Print the date and time
date --iso-8601                  # Print the ISO8601 date
date --iso-8601=ns               # Print the ISO8601 date and time
time tree                        # Time how long the tree command takes to execute
```

### Terminal Multiplexers

Start multiple terminal sessions. Active sessions persist reboots. `tmux` is more modern than `screen`.

```bash
tmux                             # Start a new session (CTRL-b + d to detach)
tmux ls                          # List all sessions
tmux attach -t                   # Reattach to a session
screen                           # Start a new session (CTRL-a + d to detach)
screen -ls                       # List all sessions
screen -R 31166                  # Reattach to a session
exit                             # Exit a session
```

### Secure Shell Protocol (SSH)

```bash
ssh hostname                     # Connect to hostname using your current user name over port 22
ssh -i foo.pem hostname          # Connect to hostname using the identity file
ssh user@hostname                # Connect to hostname using the user over port 22
ssh user@hostname -p 8765        # Connect to hostname using the user over a custom port
ssh ssh://user@hostname:8765     # Connect to hostname using the user over a custom port
```

Set default user and port in `~/.ssh/config`, so you can just enter the name next time:

```bash
$ cat ~/.ssh/config
Host name
    User foo
    Hostname 127.0.0.1
    Port 8765

$ ssh name
```

### Secure Copy

```bash
scp foo.txt ubuntu@hostname:/home/ubuntu   # Copy foo.txt into the specified remote directory
```

### Bash Profile

- bash - `.bashrc`
- zsh - `.zshrc`

```bash
# Always run ls after cd
function cd() { builtin cd; ls; }

# Prompt user before overwriting any files
alias cp='cp --interactive'
alias mv='mv --interactive'
alias rm='rm --interactive'

# Always show disk usage in a human readable format
alias df='df -h'
alias du='du -h'
```

### Bash Script

#### Variables

```bash
#!/bin/bash
foo=123                          # Initialize variable foo with 123
declare -i foo=123               # Initialize an integer foo with 123
declare -r foo=123               # Initialize readonly variable foo with 123
echo $foo                        # Print variable foo
echo ${foo}_bar                  # Print variable foo followed by _bar
echo ${foo:-'default'}           # Print variable foo if it exists otherwise print default
export foo                       # Make foo available to child processes
unset foo                        # Make foo unavailable to child processes
```

#### Environment Variables

```bash
#!/bin/bash
env                              # List all environment variables
echo $PATH                       # Print PATH environment variable
export FOO=Bar                   # Set an environment variable
```

#### Functions

```bash
#!/bin/bash
greet() {
    local world="World"
    echo $world
    return $world
}
greet "Hello"
greeting=$(greet "Hello")
```

#### Exit Codes

```bash
#!/bin/bash
exit 0                           # Exit the script successfully
exit 1                           # Exit the script unsuccessfully
echo $?                          # Print the last exit code
```

#### Conditional Statements

**Boolean Operators:**

- `$foo` — Is true
- `!$foo` — Is false

**Numeric Operators:**

- `-eq` — Equals
- `-ne` — Not equals
- `-gt` — Greater than
- `-ge` — Greater than or equal to
- `-lt` — Less than
- `-le` — Less than or equal to
- `-e foo.txt` — Check file exists
- `-v foo` — Check if variable exists

**String Operators:**

- `=` — Equals
- `==` — Equals
- `-z` — Is null
- `-n` — Is not null
- `<` — Is less than in ASCII alphabetical order
- `>` — Is greater than in ASCII alphabetical order

#### If Statements

```bash
#!/bin/bash
if [ "$foo" == 'bar' ]; then
    echo 'one'
elif [ "$foo" == 'bar' ] || [ "$foo" == 'baz' ]; then
    echo 'two'
elif [ "$foo" == 'ban' ] && [ "$USER" == 'bat' ]; then
    echo 'three'
else
    echo 'four'
fi
```

#### Inline If Statements

```bash
#!/bin/bash
[ "$USER" == 'rehan' ] && echo 'yes' || echo 'no'
```

#### While Loops

```bash
#!/bin/bash
declare -i counter
while [ $counter -gt 2 ]; do
    echo "The counter is $counter"
    counter=$((counter-1))
done
```

#### For Loops

```bash
#!/bin/bash
for i in {0..10..2}; do
    echo "Index: $i"
done

for filename in file1 file2 file3; do
    echo "Content: $filename"
done

for filename in *; do
    echo "Content: $filename"
done
```

#### Case Statements

```bash
#!/bin/bash
echo "What's the weather like tomorrow?"
read weather
case $weather in
    sunny | warm) echo "Nice weather: $weather" ;;
    cloudy | cool) echo "Not bad weather: $weather" ;;
    rainy | cold) echo "Terrible weather: $weather" ;;
    *) echo "Don't understand" ;;
esac
```

*(Original version of this guide at [https://github.com/RehanSaeed/Bash-Cheat-Sheet](https://github.com/RehanSaeed/Bash-Cheat-Sheet) — updated to reflect Kaya HPC environment)*

---

## Move Conda

### Move Conda from /home to /group

1. Navigate to your `/group`:

```bash
cd $MYGROUP
```

1. Create Conda directories in your `/group`:

```bash
mkdir -p /group/[path]/conda/envs
mkdir -p /group/[path]/conda/pkgs
```

The `-p` flag creates the environment at that specific path, and Conda will create the directory.

1. Locate the `.condarc` file (in your `/home` directory):

```bash
cd ~
```

1. Configure `~/.condarc` to point to the conda directories in `/group`:

```bash
nano ~/.condarc
```

Add these lines:

```yaml
envs_dirs:
  - /group/[path]/conda/envs

pkgs_dirs:
  - /group/[path]/conda/pkgs
```

Save and exit (`CTRL + X`, `Y`, `ENTER`).

1. Clear the cache:

```bash
conda clean --all
```

1. Log out, ssh back in.
2. Navigate to your `/group`:

```bash
cd $MYGROUP
```

1. Load Anaconda module and create packages:

```bash
module load anaconda3/2024.06
conda create -n myenv [packages]
```

---

## Quota Issues

### Transferring Data to Shared Project Directories

#### Overview

When transferring data to shared project directories on the HPC cluster, it's important to use the correct transfer commands to maintain proper group ownership. Incorrect settings can cause files to count against your personal quota instead of the project quota, potentially filling your personal disk allocation.

#### Understanding the Issue

**How Project Directories Work:**

Shared project directories (e.g., `/group/hpc000`) use a special permission setup:

```
drwxrws--- 11 root hpc000
```

The `s` in `rws` is the **setgid bit**. This special permission ensures that all files and directories created inside automatically inherit the project group (e.g., `hpc000`), which allows them to count against the project's disk quota rather than your personal quota.

**The Problem with Default Transfer Commands:**

Common transfer tools like `rsync` and `rclone` have default behaviours that can override this group inheritance:

- `rsync -a` includes the `-g` flag, which attempts to preserve the original file's group ownership from the source. This can override the setgid inheritance and assign files to your personal group instead of the project group.
- Similar issues can occur with `rclone` depending on the flags used.

**The Solution — Use Correct Transfer Flags:**

Use `rsync` without the `-g` (group preservation) flag:

```bash
# Instead of:
rsync -av source/ /group/hpc000/destination/

# Use:
rsync -av --no-g source/ /group/hpc000/destination/
```

Or, if using `rclone`:

```bash
rclone copy source remote:destination
```

Always verify after transfer that files have the correct group ownership:

```bash
ls -la /group/hpc000/destination/
```

Files should show the project group (e.g., `hpc000`) in the group column, not your personal username.

---

## WSL Issues

### Troubleshooting WSL issues

If you have issues accessing Kaya, you may need to diagnose and fix your WSL(2) configuration.

#### Diagnostics

**Check DNS Configuration:**

```bash
cat /etc/resolv.conf
```

*(shows which DNS servers WSL2 is currently using)*

**Test DNS Resolution:**

```bash
nslookup kaya.hpc.uwa.edu.au
nslookup kaya01.hpc.uwa.edu.au
```

*(compare which one resolves and which fails)*

**Check if WSL.conf exists:**

```bash
cat /etc/wsl.conf
```

*(check DNS auto-generation)*

**Get Windows DNS Servers for comparison (in PowerShell):**

```powershell
ipconfig /all | Select-String -Pattern "DNS Servers" -Context 0,3
```

*(shows which DNS servers Windows is using when VPN is connected)*

**Test Direct Query to Windows DNS (in WSL2):**

```bash
nslookup kaya01.hpc.uwa.edu.au <Windows-DNS-IP>
```

*(test if querying Windows DNS server directly works)*

**Check Routing:**

```bash
ip route show
cat /etc/hosts | grep -i kaya
```

*(check if there are any manual entries or routing issues)*

#### Resolving connection issues

If you cannot connect because WSL2 cannot resolve the internal hostname `kaya01.hpc.uwa.edu.au` using public DNS, the fix requires changing WSL2 to use UWA's internal DNS servers (`130.95.61.171` and `130.95.61.172`) instead of Google DNS (`8.8.8.8`).

**Step 1: Configure WSL2 to stop auto-generating DNS config**

```bash
sudo nano /etc/wsl.conf
```

Add these lines (or create the file if it doesn't exist):

```ini
[network]
generateResolvConf = false
```

Save and exit.

**Step 2: Update DNS servers to UWA's internal DNS**

Remove the auto-generated `resolv.conf`:

```bash
sudo rm /etc/resolv.conf
```

Create new `resolv.conf` with UWA DNS servers:

```bash
sudo nano /etc/resolv.conf
```

Add these lines:

```
nameserver 130.95.61.171
nameserver 130.95.61.172
search hpc.uwa.edu.au
```

Save and exit.

**Step 3: Restart WSL2**

In Windows PowerShell (close Ubuntu first):

```powershell
wsl --shutdown
```

Then restart Ubuntu from the Start menu.

**Step 4: Verify the fix**

In Ubuntu terminal:

```bash
# Check DNS servers are correct
cat /etc/resolv.conf

# Test resolution
nslookup kaya01.hpc.uwa.edu.au

# Try SSH connection
ssh <kaya_username>@kaya01.hpc.uwa.edu.au
```

---

## Useful Links

### Getting started with HPC

- **[HPC Carpentry — Introduction to HPC](https://www.hpc-carpentry.org/)** — Beginner-friendly lesson covering HPC concepts, connecting to a cluster, transferring files, and submitting jobs. No prior experience required.
- **[Software Carpentry — The Unix Shell](https://swcarpentry.github.io/shell-novice/)** — A practical introduction to the command line for researchers with no prior experience.

### Job submission

- **[SLURM Cheat Sheet](https://slurm.schedmd.com/)** — Quick reference for common SLURM commands
- **[SLURM Quick Start Guide](https://slurm.schedmd.com/quickstart.html)** — Getting started with job submission, with worked examples
- **[Tmux Cheat Sheet](https://tmuxcheatsheet.com/)** — Terminal multiplexer reference
- **[Screen Cheat Sheet](https://gist.github.com/jctosta/af918e1618682638aa82)** — Screen terminal multiplexer reference

### Software & containers

- **[Apptainer Documentation](https://apptainer.org/docs/)** — Official user guide for Apptainer (formerly Singularity)
- **[Conda Documentation](https://docs.conda.io/)** — Package and environment management
- **[Bioconda](https://bioconda.github.io/)** — Bioinformatics packages for Conda

### Data management

- **[UWA Research Data Hub](https://research.uwa.edu.au/research-data/)** — Research Data Management Plans and UWA data management guidance
- **[UWA Library — FAIR & CARE](https://www.library.uwa.edu.au/research/research-data/fair-data)** — UWA's guidance on FAIR principles and the UWA Research Integrity Policy requirements
- **[ARDC — Making Data FAIR](https://ardc.edu.au/resources/working-with-data/fair-data/)** — Practical Australian guidance on applying FAIR principles to research data
- **[ARDC — FAIR Principles for Research Software](https://ardc.edu.au/resources/working-with-data/fair-data/fair-software/)** — Applying FAIR to research software outputs
- **[GO FAIR — FAIR Principles](https://www.go-fair.org/fair-principles/)** — The authoritative reference for the FAIR principles
- **[Wilkinson et al. 2016 — The FAIR Guiding Principles](https://doi.org/10.1038/sdata.2016.18)** — The original paper defining FAIR (Scientific Data)

### Getting help

- **[Request HPC support](https://uwa.service-now.com/)** — Submit a support ticket via ServiceNow
- **[Request a new project](https://uwa.service-now.com/)** — Apply for a new project allocation
- **Email:** [hpc-admin@uwa.edu.au](mailto:hpc-admin@uwa.edu.au)

---

# About Kaya

---

## Events and Dates

### Regular Events

System maintenance is scheduled on the **second Tuesday of every month**.

Parts or all of the HPC system may be unavailable from **8am to 4pm** on that day.

If an outage will cause significant impact on project deliverables, please contact the HPC team to see what mitigations may be possible. Please note however that postponing or cancelling planned maintenance is unlikely to be possible.

### Support Sessions

The HPC team are currently located in the **Roberts Street building, room 102**. Please contact us by email at [hpc-admin@uwa.edu.au](mailto:hpc-admin@uwa.edu.au) if you wish to schedule time for a support session.

---

## What is Kaya

Kaya is the name of the UWA IT HPC management system. The Kaya system is primarily used to act as a 'launch pad' to enable researchers to model their computational workloads with a view to successfully migrating into other systems such as Pawsey, Nectar cloud, or other commercial clouds.

All proposed projects that are planning to use the Pawsey Supercomputing Research Centre or National Compute Infrastructure facilities need to include a technical assessment of the project to ensure that it can run on the HPC systems and meet some minimum requirements around the technical feasibility and the quality of research project itself.

The UWA HPC team's role in this process is to help researchers:

- Migrate their applications to the UWA HPC environment.
- Become familiar with using the resource management tool — Slurm.
- Develop the skills necessary to transition from using a GUI based environment to using the command line.
- Develop the scaling studies and benchmarks required for the technical assessment as part of a successful NCMAS/Pawsey allocation.

### Kaya Resources

The Kaya resources contain a number of compute nodes that are available to UWA researchers to use to test and model workloads.

#### Compute

- **4 × Large GPU nodes**, each with 36 cores, 750 GB RAM, 3 TB Solid State local scratch storage, 2 × nVidia Tesla V100 GPUs with 32 GB RAM each.
- **12 × Medium CPU-only nodes**, each with 20 or 28 cores, 250 GB RAM, 2–5 TB local scratch storage.
- **12 × Small CPU-only nodes**, each with 12 cores, 48 GB RAM, 2 TB local scratch storage.

#### Storage

The Kaya compute nodes are networked to a Pure Flashblade storage system with approximately 100 TB of available storage in total. This Flashblade is partitioned to provide both scratch space for running jobs and project (or group) storage for storing research data. This is high performance storage that is strictly for data being used by active projects. HPC storage is not intended to be used for long term storage or data archiving. Long term storage is provided by IRDS (Institutional Research Data Storage) here at UWA and your RDM (Research Data Management) plans should reflect this.

**Storage on Kaya is not backed up** (per normal HPC site conventions).

#### Network

The HPC system uses an internal 100 Gb Ethernet network to link internal components. This provides high throughput internal connectivity.

Kaya does not currently have low latency internal connectivity (e.g. Infiniband), though this is a planned enhancement.

#### Resource Management

Kaya uses the SLURM scheduler for resource management. Walltimes up to 3 days are currently available on the system.

The 3 day queue is provided to allow researchers to quantify the runtimes and gain better insight into application performance in preparation for migrating work to the Pawsey Centre. Note that maximum walltimes allowed at Pawsey are 24 hours.

### Kaya Projects

Kaya is currently a very small system and as such cannot support long-term projects. Projects on Kaya are expected to be modest in scale and have a defined start and end point. In addition to meeting the research goals it is expected that outcomes of a successful project on Kaya will include:

- The researcher has better insight and understanding of their application performance.
- The researcher has a better understanding of the computing resources that they require for their research.
- That the researcher will be able to migrate future computational workloads to national facilities such as the Pawsey Supercomputing Research Centre via the National Computer Merit Allocation Scheme (NCMAS) or the Pawsey Partner scheme.
- That the UWA HPC team can identify any short-comings in the current offerings in the UWA research computing eco-system.

> A PhD is not a "modest" project, but a collection of smaller projects with a focused goal.

Keeping Kaya projects modest allows the UWA HPC team to manage resource consumption on the system, especially data storage, and keep this valuable resource available to as many researchers as possible in the UWA community.

More information on the process to request accounts on Kaya is provided in the [Applying for Access](#applying-for-access) section.

---

## Acknowledging Kaya

To comply with the policies of the Office of Research UWA (Policy library | The University of Western Australia), specifically "Research Integrity Guidelines" (Item K), researchers should formally acknowledge the computational resources and technical guidance of Kaya and the HPC team where they have been of benefit to the research.

Upon project completion, we ask that all researchers share any outputs from their work on Kaya with the HPC team. This includes published papers, conference presentations, or other research outcomes. We also request that you include an acknowledgement of Kaya in any publications or presentations, as follows:

> "The authors acknowledge the use of Kaya, the High Performance Computing facility at The University of Western Australia, and the technical assistance provided by the UWA IT - HPC team."
> [https://doi.org/10.26182/dh5s-v482](https://doi.org/10.26182/dh5s-v482)

Please notify us of your research outcomes via email: [hpc-admin@uwa.edu.au](mailto:hpc-admin@uwa.edu.au)

---

## Kaya Fine Print

### Kaya Usage Guidelines

The UWA IT HPC Kaya service provides high performance computing to faculty and students at the University of Western Australia. Kaya users are expected to adhere to the Acceptable Use of IT, Cyber Security Policies and Academic Integrity Policies of the University of Western Australia.

### Accounts and Data Retention Policy

Accounts on Kaya are available to UWA faculty, their collaborators and students either working with them or in a class that requires access to Kaya.

#### Allocations to Resources

All access to Kaya resources (clusters, servers, project storage) is granted and revoked via project allocations. Project allocations are managed by Principal Investigators (PI).

#### Yearly Project Review

Faculty are required to review their projects and verify all accounts in their group on a yearly basis. If there is no activity for one year, all accounts in the group will be deleted and data associated with the project, including user home directories, will be deleted.

> **NOTE:** Data in expired accounts will not be migrated when there are changes to the UWA HPC storage systems. If you want your data, we recommend you follow an appropriate data management plan.

### Faculty

**Account** — When a faculty member leaves the University, access to the UWA network will be removed as soon as your employment ends. Unless arrangements have been made, your UWA IT HPC account will be terminated at the same time as your UWA account.

**Data** — All data owned by your account on our systems will be deleted within 30 days of account termination. This includes data on Kaya's network attached storage systems (user & project directories), local compute node and global scratch directories, and data stored on servers owned by the faculty group (if applicable).

> **IMPORTANT:** When a faculty member leaves behind students at UWA, arrangements MUST be made with those students and another faculty member to take over their account sponsorship. Student accounts must be sponsored by an active UWA faculty member, so unless prior arrangements have been made, when a faculty member leaves, any accounts sponsored by them are also terminated and data is removed.

### Students — Class Accounts

**Account** — Accounts provided for class work are valid for the semester that the class is offered in and automatically terminated at the end of the semester. If a student requires additional time to complete coursework, the professor teaching the course must contact UWA help to request an extension on the account. Student accounts that are also sponsored by a faculty member remain active after the course ends, subject to the policies in the "faculty sponsored accounts" section below.

**Data** — Data in a student's home directory created for a class account is deleted 30 days after account termination. This includes data on Kaya's network attached storage systems (user & course project directories), local compute node and global scratch directories, and cloud instances and storage (if applicable).

**Usage** — Usage of the cluster by students in a class is reported back to the instructor of the class. Requests for assistance, software installations, or other communications by students to UWA IT HPC staff could potentially be shared with the instructor.

### HDR and Honours Students — Faculty Sponsored Accounts

**Account** — An account sponsored by a faculty member is terminated when a student leaves the University of Western Australia or when the sponsoring faculty member requests the student's access to Kaya be removed. If a faculty member wants a student to continue to access Kaya resources after leaving the university, a request must be made to UWA Service Now portal. The account will then be moved under the "non-UWA collaborator" category of accounts (see below).

**Data** — Data stored on Kaya's network attached storage systems in the user's home directory and local compute node scratch directories are deleted when the student's account is terminated. If there is data stored by the student in a faculty member's project directory, this data is not removed. It is up to the faculty member to manage the data in their project and global scratch spaces.

**Usage** — Usage of the cluster by students is reported to the faculty member sponsoring the student's account. Requests for assistance, software installations, or other communications by students to UWA IT HPC staff could potentially be shared with that faculty member as well.

### Non-UWA Collaborators

**Account** — Accounts granted to non-UWA collaborators are dependent on the sponsorship of a UWA faculty member. If at any time, the sponsor of your account wants your access to Kaya resources cut off, we are required to terminate the account.

**Data** — Data stored on Kaya's network attached storage systems in the user's home directory and local compute node scratch directories are deleted when the account is terminated. If there is data stored by the collaborator in a sponsor's project directory, global scratch directory, or research cloud, this data is not removed. It is up to the sponsor (UWA faculty member) to manage the data in these spaces.

### Links to UWA and UWA IT HPC Specific Guidelines

- UWA Acceptable Use of IT
- Cyber Security Policy
- UWA IT HPC Use and Misuse of HPC Resources Guidelines
- UWA IT HPC Kaya Accounts and Data Retention Guidelines
- UWA Academic Integrity for Students

### Breach of Guidelines

Failure to comply with these guidelines and the UWA policies by a member of the University Community may be considered a breach of the Code of Conduct and may result in disciplinary action.

---

*Documentation source: [https://docs.hpc.uwa.edu.au](https://docs.hpc.uwa.edu.au) — UWA HPC Documentation*