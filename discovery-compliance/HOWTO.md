# Discovery Compliance - Codex Skill

*This is a skill that you can install in your Codex app*

## Requirements

### OpenAI Codex

This is a skill that runs inside OpenAI's Codex app.

#### Installing OpenAI Codex

You can install Codex from this link: [Install Page](https://developers.openai.com/codex/app/)


### Python

Your system must have Python installed. If you have a Mac, you probably already have Python installed. If you have a Windows computer, you may need to install Python.

#### Checking for Python

The easiset way to tell if you have Python installed is to open a terminal window ([Mac](https://support.apple.com/guide/terminal/open-or-quit-terminal-apd5265185d-f365-44cb-8b09-71a064a42125/mac) or [Windows](https://learn.microsoft.com/en-us/answers/questions/5637237/how-to-open-command-prompt-in-windows-11)) on your computer, and enter the following command:

```text
$ python --version
```

You will get back a response telling you what version of Python is installed on your system if you have Python. Otherwise, you'll get an error, which means you need to install Python.

#### Installing Python

You can install Python from these links:

* Windows [Installer](https://www.python.org/ftp/python/3.13.12/python-3.13.12-amd64.exe)
* Mac [Installer](https://www.python.org/downloads/release/python-3143/)

## Installing the Skill

To install the skill, open the Codex app and enter this prompt:

```text
Use $skill-installer to install the skill from https://github.com/tjdaley/codex_skills/tree/main/discovery-compliance
```

## Using the Skill

Here is the flow of the skill:

![Discovery Compliance Skill Flowchart](https://github.com/tjdaley/codex_skills/blob/main/discovery-compliance/_GUMROAD%20Discovery%20Compliance%20-%20Flowchart%20(Zoom%20Virtual%20Background).png)

**First**: In the Codex App, look for the "Threads" heading in the lefthand menu. Next to it, you'll see an icon of a folder with a plus symbol. Click that icon and create a new project. I recommend naming the project after the legal matter you are working on. For example, if you represent Jane Doe in a divorce matter, create a project called "DOE, JANE - Divorce". The name of the project is not important to the skill, but you'll want to keep each client separate.

**Second**: Within the project folder, create two more folders:

1. Our Production
2. Their Production

**Third**: Copy the documents to be analyzed into folders in the project directory.

1. Copy all the bank statements that _**we**_ produced into a "Bank Statements" folder under "Our Production"
2. Copy all the credit card statements that _**we**_ produced into a "Credit Card Statements" folder under "Our Production"
1. Copy all the bank statements that _**they**_ produced into a "Bank Statements" folder under "Their Production"
2. Copy all the credit card statements that _**they**_ produced into a "Credit Card Statements" folder under "Their Production"

It's OK for the folders to have nested folders. The skill will go through all the folders to find what it needs.

When you have finished copying the statements you want to analyze, your folder structure might look something like this:

```text
DOE, JANE - Divorce
 |- Our Production
 |---- Bank Statements
 |-------- Wells Fargo
 |-------- Capital One
 |-------- Bank of America
 |---- Credit Card Statements
 |-------- American Express
 |-------- Home Depot
 |-------- Chase Saphire
 |- Their Production
 |---- Bank Statements
 |---- Credit Card Statements
```

The folder structure doesn't matter to the skill, but you do want all bank statements in one place, by themselves, and all credit card statements in one place, by themselves.

**Fourth**: Use the Skill

Go back to the Codex app and click on the project you created, "DOE, JANE - Divorce" in this example.

Create a new thread in that project by clicking the ```New Thread``` button at the top left of the app's menu.

Enter this prompt in the Codex app:

```text
Use $discovery-compliance to extract statement metadata and build compliance matrices for discovery production.
```

**Fifth**: Answer the skill's questions.

The skill will ask you these questions:

```text
Send these and I'll run the skill workflow for you:

  1. Bank statement folder path, if any.
  2. Credit card statement folder path, if any.
  3. Output folder path.
  4. Matter-specific Bates regex.
  5. Matrix year range, like 2020 to 2026
 
If you want, I can also search your OneDrive for likely statement folders and propose the paths.
```

You should reply as follows:

```text
1. [path to folder]\Codex\DOE, JANE - Divorce\Our Production\Bank Statements
2. [path to folder]\Codex\DOE, JANE - Divorce\Our Production\Credit Card Statements
3. [path to folder]\Codex\DOE, JANE - Divorce\Our Production
4. JD0+\d{4}
5. 2020 - 2026
```

*Putting the question number in front of your answer helps the skill correlate your response to its questions.*

This tells the skill where to find the files to analyze and where to save the spreadsheets it creates.

The "Matter-specific Bates regex" is a little more complicated. "Regex" means "regular expression" which is a technical term for "search pattern." For example, in the example above, the partes of the regular expression have these meanings:

Part | Meaning
----|----
JD | Bates numbers start with the letters "JD"
0+ | The letters are followed by one or more zeros
\d{4} | The zeros are followed by at least 4 numeric digits (which could be zeros)

Likewise, if your Bates numbers start with some longer text sequence, such as "Produced by Jane Doe on June 3, 2025: JD000123", you would use a regular expression like this:

```Produced by Jane Doe .*JD0+\d{4}```

Part | Meaning
----|----
Produced by Jane Doe | The fixed preamble to the Bates number
.* | The preamble is followed by any number of other characters
JD | The beginning of the real Bates number is "JD"
0+ | Followed by one or more zeros
\d{4} | Followed by at least 4 numberic characters (which could be zeros)

**Finally**: The skill will run through the input folders and create the output spreadsheets. It may ask you some questions while it runs, depending on your computer's configuration. Generally, just say "YES" to whatever it asks (if it's a yes or no question). When it's done, you'll get a pop-up message telling you it's done and you'll find the output spreadsheet in the output folder, in this example ```[path to folder]\Codex\DOE, JANE - Divorce\Our Production```.

## Thank You

Thank you for installing and using this skill. I hope it helps you ananlyze discovery deficiecies quickly and accurately and that you get to spend more time enjoying life than pouring over folders of documents.

## Author

Thomas J. Daley, J.D.
[Web Site](https://tjd.txfamlaw.com)
[Law Firm](https://koonsfuller.com/attorneys/tom-daley)
[Blog](https://www.thomasjdaley.com)
[Law Firm Automation](https://www.jdbot.us)
[LinkedIn](https://www.linkedin.com/in/tomdaley/)

_Copyright &copy; 2026 by Thomas J. Daley. All Rights Reserved._


    
