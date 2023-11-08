`stacky` is a homebrewed tool to manage stacks of PRs. This allows developers to easily manage many smaller, more targeted PRs that depend on each other.


## Installation
`stacky` requires the following python3 packages installed on the host 
1. asciitree
2. ansicolors
3. simple-term-menu
```
sudo pip3 install asciitree ansicolors simple-term-menu
```

## Usage
`stacky` stores all information locally, within your git repository
Syntax is as follows:
- `stacky info`: show all stacks , add `-pr` if you want to see GitHub PR numbers (slows things down a bit)
- `stacky branch`: per branch commands (shortcut: `stacky b`)
    - `stacky branch up` (`stacky b u`): move down the stack (towards `master`)
    - `stacky branch down` (`stacky b d`): move down the stack (towards `master`)
    - `stacky branch new <name>`: create a new branch on top of the current one
- `stacky commit [-m <message>] [--amend] [--allow-empty]`: wrapper around `git commit` that syncs everything upstack
- Based on the first argument (`stack` vs `upstack` vs `downstack`), the following commands operate on the entire current stack, everything upstack from the current PR (inclusive), or everything downstack from the current PR:
    - `stacky stack info [--pr]`
    - `stacky stack sync`: sync (rebase) branches in the stack on top of their parents
    - `stacky stack push [--no-pr]`: push to origin, optionally not creating PRs if they don’t exist
- `stacky upstack onto <target>`: restack the current branch (and everything upstack from it) on top of another branch (like `gt us onto`), useful if you’ve made a separate PR that you want to include in your stack
- `stacky continue`: continue an interrupted stacky sync command (because of conflicts)
- `stacky update`: will pull changes from github and update master

The indicators (`*`, `~`, `!`) mean:
- `*` — this is the current branch
- `~` — the branch is not in sync with the remote branch (you should push)
- `!` — the branch is not in sync with its parent in the stack (you should run `stacky stack sync`, which will do some rebases)

```
$ stacky --help
usage: stacky [-h] [--color {always,auto,never}]
              {continue,info,commit,amend,branch,b,stack,s,upstack,us,downstack,ds,update,import,adopt,land,push,sync,checkout,co,sco} ...

Handle git stacks

positional arguments:
  {continue,info,commit,amend,branch,b,stack,s,upstack,us,downstack,ds,update,import,adopt,land,push,sync,checkout,co,sco}
    continue            Continue previously interrupted command
    info                Stack info
    commit              Commit
    amend               Shortcut for amending last commit
    branch (b)          Operations on branches
    stack (s)           Operations on the full current stack
    upstack (us)        Operations on the current upstack
    downstack (ds)      Operations on the current downstack
    update              Update repo
    adopt               Adopt one branch
    land                Land bottom-most PR on current stack
    push                Alias for downstack push
    sync                Alias for stack sync
    checkout (co)       Checkout a branch
    sco                 Checkout a branch in this stack

optional arguments:
  -h, --help            show this help message and exit
  --color {always,auto,never}
                        Colorize output and error
```

### Sample Workflow 
1. Create a new working branch with `stacky branch new <branch_name>`. 
2. Update files and add files to git tracking like normal (`git add`)
3. Commit updates with `stacky commit -m <commit_message>`
4. Create a stacked branch with `stacky branch new <downstack_branch_name>`
5. Update files and add files in downstack branch (`git add`)
6. `stacky push` will create 2 PRs. Top branch will have a PR against master and bottom branch will have a PR against the top branch.
7. Update the upstack branch and run `stacky commit`. This will rebase changes in the upstack branch to the downstack branch
8. `stacky push` will update both the PRs.
