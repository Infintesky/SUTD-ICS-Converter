# SUTD-ICS-Converter

Convert SUTD SAMS class schedule HTML to ICS (iCalendar) format for import into calendar applications.

## Usage

1. Log in to SUTD SAMS and open your class schedule
2. Switch the display to List View
3. Right-click on the page and select "Open frame in new tab"
4. Save the page as an HTM file (e.g., `class.htm`)
5. Run the parser:

```bash
python parser.py <htm file>
```

6. Import the generated `class.ics` file into your calendar app (Google Calendar, Apple Calendar, Outlook, etc.)

## Output

The parser extracts:
- Course names
- Class schedules (day and time)
- Locations
- Component types (Lecture, Cohort, etc.)

Events are created with the Singapore timezone (Asia/Singapore).
