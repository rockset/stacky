`stacky` is a homebrewed tool to manage stacks of PRs. This allows developers to easily manage many smaller, more targeted PRs that depend on each other.


## Installation
### Pip
```
pip3 install rockset-stacky
```

### Manual
`stacky` requires the following python3 packages installed on the host 
1. asciitree
2. ansicolors
3. simple-term-menu
```
sudo pip3 install asciitree ansicolors simple-term-menu
```
Stacky doesn't use any git or Github APIs. It expects `git` and `gh` cli commands to work and be properly configured. For instructions on installing the github cli `gh` please read their [documentation](https://cli.github.com/manual/).

After which `stacky` can be directly run with `./stacky`. We would recommend symlinking `stacky` into your path so you can use it anywhere

## Usage
`stacky` stores all information locally, within your git repository
Syntax is as follows:
- `stacky info`: show all stacks , add `-pr` if you want to see GitHub PR numbers (slows things down a bit)
- `stacky branch`: per branch commands (shortcut: `stacky b`)
    - `stacky branch up` (`stacky b u`): move down the stack (towards `master`)
    - `stacky branch down` (`stacky b d`): move down the stack (towards `master`)
    - `stacky branch new <name>`: create a new branch on top of the current one
- `stacky commit [-m <message>] [--amend] [--allow-empty]`: wrapper around `git commit` that syncs everything upstack
    - `stacky amend`: will amend currently tracked changes to top commit
- Based on the first argument (`stack` vs `upstack` vs `downstack`), the following commands operate on the entire current stack, everything upstack from the current PR (inclusive), or everything downstack from the current PR:
    - `stacky stack info [--pr]`
    - `stacky stack sync`: sync (rebase) branches in the stack on top of their parents
    - `stacky stack push [--no-pr]`: push to origin, optionally not creating PRs if they don’t exist
- `stacky upstack onto <target>`: restack the current branch (and everything upstack from it) on top of another branch (like `gt us onto`), useful if you’ve made a separate PR that you want to include in your stack
- `stacky continue`: continue an interrupted stacky sync command (because of conflicts)
- `stacky update`: will pull changes from github and update master, and deletes branches that have been merged into master

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

```
$> stacky branch new change_part_1
branch 'change_part_1' set up to track 'master'.
$> touch adding_new_file
$> git add adding_new_file
$> stacky commit -m "Added new file"
[change_part_1 23b102a] Added new file
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 adding_new_file
~* change_part_1
✓ Not syncing branch change_part_1, already synced with parent master
$> stacky branch new change_part_2
branch 'change_part_2' set up to track 'change_part_1'.
$> touch second_file
$> git add second_file
$> stacky commit -m "Added second file"
[change_part_2 0805f57] Added second file
 1 file changed, 0 insertions(+), 0 deletions(-)
 create mode 100644 second_file
~* change_part_2
✓ Not syncing branch change_part_2, already synced with parent change_part_1
$> stacky info
 │   ┌── ~* change_part_2
 ├── ~ change_part_1
master
$> stacky push
     ┌── ~* change_part_2
 ┌── ~ change_part_1
master
✓ Not pushing base branch master
- Will push branch change_part_1 to origin/change_part_1
- Will create PR for branch change_part_1
- Will push branch change_part_2 to origin/change_part_2
- Will create PR for branch change_part_2

Proceed? [yes/no] yes
Pushing change_part_1
Creating PR for change_part_1
? Title change part 1
? Body <Received>
? What's next? Submit as draft
https://github.com/rockset/stacky/pull/2
Pushing change_part_2
Creating PR for change_part_2
? Title Added second file
? Body <Received>
? What's next? Submit as draft
https://github.com/rockset/stacky/pull/3
$> git co change_part_1
$> vim adding_new_file
$> git add adding_new_file
$> stacky commit -m "updated new file"
[change_part_1 aa06f71] updated new file
 1 file changed, 1 insertion(+)
 ┌── !~ change_part_2
~* change_part_1
✓ Not syncing branch change_part_1, already synced with parent master
- Will sync branch change_part_2 on top of change_part_1
```

## License
MIT License

Copyright (c) 2023 Rockset
Permission is hereby granted, free of charge, to any person obtaining a copy 
of this software and associated documentation files (the “Software”), to deal 
in the Software without restriction, including without limitation the rights 
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
copies of the Software, and to permit persons to whom the Software is 
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all 
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, 
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE 
SOFTWARE.
