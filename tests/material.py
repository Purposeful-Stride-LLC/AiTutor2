"""Realistic (if short) source text for tests: enough words to pass the source check."""

SHELL_TEXT = """# Pipes and filters

A pipe sends the output of one program straight into the input of the next program.
The shell builds a pipeline when you join commands with the vertical bar character, and
each program in the pipeline runs at the same time as the others. Programs that read text on
their input, change it, and write text on their output are called filters. Common filters
include sort, uniq, head, tail, cut and wc. Because every filter speaks plain text, you can
join them in any order to answer a question about your data.

# Searching with grep

The grep program is a filter that prints only the lines that match a pattern. You can give it
a plain word or a regular expression. The option -i ignores case, -v prints the lines that do
not match, and -c counts the matching lines instead of printing them. A common pipeline is to
list the files in a folder and pipe that list into grep to find the names you need. Another is
to search a log file for the word error and pipe the result into wc to count the problems.

# Active voice

The active voice is usually more direct and vigorous than the passive. When you write notes
about a pipeline, say what each program does: grep keeps the matching lines, sort orders them,
and uniq removes the repeated lines that sit next to each other.
"""
