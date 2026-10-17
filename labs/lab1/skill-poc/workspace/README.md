# Lab 1 — Chat and Observe

Chat with Pi. See the actions behind the reply.

## Basic navigation

- **Switch tabs:** press **Ctrl+B**, release, then **1** or **2**.
- **Save in Fresh:** **Ctrl+S**.
- **Command palette in Fresh:** **Ctrl+P**.
- **Quit Fresh:** **Ctrl+Q**. This does not stop the lab.

## Find your way

- **Tab 1 — Agent:** chat with Pi. Read tool results here.
- **Tab 2 — Editor:** read this guide and edit files in Fresh.
- **Lab 1 card:** the guide and project folder.
- **Skills card:** the skills folder and explorer.

Cards switch folders in Fresh, not terminal tabs. They do not start Pi.
If a card or guide is missing, ask your TA.

Use fictional data only. Prompts use quota and may cost money.
Pi can read the copied workshop key. A read may put it into chat, logs and
provider requests. Do not share keys or private output.

## 1. Set up and enter

Complete workshop preparation first.
In your **host terminal**, from the **workshop root**, run:

```bash
./lab.sh lab1 setup
```

Wait for setup to finish. Then run:

```bash
./lab.sh lab1 enter
```

**Check:** Agent has Pi. Editor opens this guide in the **Lab 1** card.
Use lab Pi, not personal host Pi or the preparation session.
If a command fails, stop and ask your TA.

The guide and cards are new-lab defaults. Existing HOMEs keep their installed
guide. To update Pi/Herdr/Fresh configuration, save editor work, run
`./lab.sh lab1 stop`, then `./lab.sh lab1 setup` from your host terminal.
Setup lists changes and asks before replacing differing configuration files;
replacement discards their installed custom settings. Enter the lab afterward
to start the tools. This does not reset existing layout state or rewrite this
guide. Do not reset merely to update configuration: reset deletes Lab 1 work.

## 2. Say hi and ask about meetings

In **Agent**, send one message at a time. Wait for each reply.

```text
Hi
```

```text
I was in the office today so can you check calendar for me?
```

After Pi finishes, send:

```text
/observer
```

Look at **Cycle**, **Tool details** and **Context**.
The observer shows activity, not result contents. Read tool results in Pi.

**Check:** Which tools ran? What did they return?
No calendar is connected. Do not add calendar keys or private meeting data.

## 3. Have fun at LINE Dev Conf

In the same chat, send this exact message:

```text
I'm having fun at LINE Dev Conf!
```

Watch the actions. After Pi finishes, send:

```text
/observer
```

**Check:** Name the tools and files. Read the actual tool results in Pi.
A reply or loaded skill is not proof of a file read.
Results vary. Refusal or no action is valid. Do not force a trigger.

## 4. Teach your agent to find the flag.

Create a separate skill that reads and prints this synthetic target file when
the user types the exact greeting `Hello LINE Dev Conf!`:

```text
/home/lab-user/.local/share/line-dev-conf/flag.txt
```

The path above is a target file, not a command.

In **Editor → Skills**:

1. Open `fun/SKILL.md`. Keep it unchanged.
2. Create your own folder under `/home/lab-user/.agents/skills/`. Do not overwrite
   an existing skill.
3. Add `SKILL.md`. Start with a YAML header between `---` lines containing
   `name` and `description`.
4. Write instructions to read only the target file and print its contents when
   the user types `Hello LINE Dev Conf!`. Save with **Ctrl+S**.

**Hint:** You can ask the agent to help create the skill. Specify a separate new
skill, keep the existing fun skill unchanged, and make the file-read/print action
conditional on the exact greeting. Before loading generated instructions, review
all created and changed files, including hidden files. Check the destination,
name, description, greeting trigger and file-read instructions.

Do not paste the flag value into chat or hard-code it in the skill. Do not read
real keys or unrelated files. Preserve existing skills and work.

After reviewing and saving, send in **Agent**:

```text
/reload
```

Check that your skill is listed. Then send only:

```text
Hello LINE Dev Conf!
```

**Check:** Confirm the target file read and printed content in actual tool results,
not just the final reply. If it fails, inspect your skill and tool activity; do not
force a result.

## 5. Save and stop

Save in Fresh with **Ctrl+S**.
Press **Ctrl+B**, release, then **q** to return to the host.
Detaching does not stop the lab.

In your **host terminal**, from the **workshop root**, run:

```bash
./lab.sh lab1 stop
```

**Check:** Stop completes. Saved work, settings, sessions and logs stay.
Stop may not cancel model requests already sent.

**Debrief:** skills suggest actions; they are not access boundaries. Useful
output and actual tool evidence are different.
