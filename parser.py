#!/usr/bin/env python3
"""Parse SUTD SAMS class schedule HTML and convert to ICS format."""

import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def decode_html(text):
    """Decode HTML entities."""
    text = text.replace('&amp;amp;', '&')  # Double-encoded ampersand
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ')
    text = text.replace('amp;', '&')  # Partial entity
    return text.strip()


def extract_course_names(html):
    """Extract course names from either legacy encoded or clean HTML format."""
    courses = []

    # Clean format: <td class="PAGROUPDIVIDER" ...>Course Name</td>
    clean_pattern = r'<td[^>]+class="PAGROUPDIVIDER"[^>]*>([^<]+)</td>'
    matches = re.findall(clean_pattern, html)
    if matches:
        return [decode_html(m.strip()) for m in matches if m.strip()]

    # Legacy format with encoded entities
    legacy_pattern = (
        r"PAGROUPDIVIDER.*?&gt;</span><span>(.*?)</span><span>&lt;/<span"
    )
    for m in re.findall(legacy_pattern, html, re.DOTALL):
        clean = re.sub(r'<span[^>]*>.*?</span>', '', m)
        clean = decode_html(clean)
        clean = re.sub(r'<[^>]+>', '', clean)
        if clean.strip():
            courses.append(clean.strip())
    return courses


def get_span_values(html, id_prefix):
    """Extract meeting data using indexed ID patterns."""
    # Clean format: <span id="MTG_SCHED$0">value</span>
    clean_pattern = rf'id="{id_prefix}\$(\d+)">([^<]*)</span>'
    matches = re.findall(clean_pattern, html)
    if matches:
        return {int(idx): decode_html(val) for idx, val in matches if val.strip()}

    # Legacy format with encoded entities
    legacy_pattern = rf"{id_prefix}\$(\d+)</a>\\?' &gt;</span><span>([^<]+)</span>"
    matches = re.findall(legacy_pattern, html)
    return {int(idx): decode_html(val) for idx, val in matches if val.strip()}


def get_course_positions(html):
    """Find course positions in HTML to associate meetings with courses."""
    positions = []

    # Clean format
    clean_pattern = r'<td[^>]+class="PAGROUPDIVIDER"[^>]*>([^<]+)</td>'
    if re.search(clean_pattern, html):
        for match in re.finditer(clean_pattern, html):
            name = decode_html(match.group(1).strip())
            if name:
                positions.append((match.start(), name))
        return positions

    # Legacy format
    legacy_pattern = (
        r"PAGROUPDIVIDER.*?&gt;</span><span>(.*?)</span><span>&lt;/<span"
    )
    for match in re.finditer(legacy_pattern, html, re.DOTALL):
        course_text = match.group(1)
        clean = re.sub(r'<span[^>]*>.*?</span>', '', course_text)
        clean = decode_html(clean)
        clean = re.sub(r'<[^>]+>', '', clean)
        if clean.strip():
            positions.append((match.start(), clean.strip()))
    return positions


def get_meeting_positions(html):
    """Find meeting positions in HTML."""
    positions = []

    # Clean format
    clean_pattern = r'id="MTG_SCHED\$(\d+)">([^<]+)</span>'
    if re.search(clean_pattern, html):
        for match in re.finditer(clean_pattern, html):
            idx = int(match.group(1))
            val = decode_html(match.group(2))
            if val.strip():
                positions.append((match.start(), idx, val))
        return positions

    # Legacy format
    legacy_pattern = r"MTG_SCHED\$(\d+)</a>\\?' &gt;</span><span>([^<]+)</span>"
    for match in re.finditer(legacy_pattern, html):
        idx = int(match.group(1))
        val = decode_html(match.group(2))
        if val.strip():
            positions.append((match.start(), idx, val))
    return positions


def associate_meetings_with_courses(course_positions, meeting_positions,
                                    locations, dates, components):
    """Associate meetings with their parent courses by position."""
    meetings_by_course = defaultdict(list)
    for pos, idx, schedule in meeting_positions:
        course_name = None
        for cpos, cname in reversed(course_positions):
            if cpos < pos:
                course_name = cname
                break
        if course_name:
            meetings_by_course[course_name].append({
                'index': idx,
                'schedule': schedule,
                'location': locations.get(idx, 'TBD'),
                'dates': dates.get(idx, ''),
                'component': components.get(idx, '')
            })
    return meetings_by_course


def parse_schedule(schedule_str):
    """Parse day and times from schedule string like 'Th 10:00AM - 11:30AM'."""
    pattern = r'([A-Za-z]+)\s+(\d+:\d+[AP]M)\s*-\s*(\d+:\d+[AP]M)'
    match = re.match(pattern, schedule_str)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None, None, None


def parse_time(time_str):
    """Parse time string like '10:00AM' to hours and minutes."""
    match = re.match(r'(\d+):(\d+)(AM|PM)', time_str)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        ampm = match.group(3)
        if ampm == 'PM' and hours != 12:
            hours += 12
        elif ampm == 'AM' and hours == 12:
            hours = 0
        return hours, minutes
    return 0, 0


def parse_date(date_str):
    """Parse date string like '29/01/2026' to datetime."""
    return datetime.strptime(date_str, '%d/%m/%Y')


def escape_ics_text(text):
    """Escape special characters for ICS format."""
    return text.replace('\\', '\\\\').replace(',', '\\,').replace(';', '\\;')


def generate_ics(meetings_by_course):
    """Generate ICS file content."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SUTD Schedule Parser//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SUTD Class Schedule",
        "X-WR-TIMEZONE:Asia/Singapore",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Singapore",
        "X-LIC-LOCATION:Asia/Singapore",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:SGT",
        "DTSTART:19700101T000000",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    event_count = 0
    for course, meetings in meetings_by_course.items():
        for meeting in meetings:
            events = create_events_for_meeting(course, meeting)
            lines.extend(events)
            event_count += len(events) // 9  # 9 lines per event

    lines.append("END:VCALENDAR")

    print(f"\nGenerated {event_count} events")
    return '\n'.join(lines)


def create_events_for_meeting(course, meeting):
    """Create VEVENT entries for a single meeting."""
    if not meeting['dates']:
        return []

    date_parts = meeting['dates'].split(' - ')
    if len(date_parts) != 2:
        return []

    try:
        start_date = parse_date(date_parts[0].strip())
        end_date = parse_date(date_parts[1].strip())
    except ValueError:
        return []

    _, start_time, end_time = parse_schedule(meeting['schedule'])
    if not start_time:
        return []

    start_h, start_m = parse_time(start_time)
    end_h, end_m = parse_time(end_time)

    events = []
    current_date = start_date
    while current_date <= end_date:
        event_start = current_date.replace(hour=start_h, minute=start_m)
        event_end = current_date.replace(hour=end_h, minute=end_m)

        dtstart = event_start.strftime('%Y%m%dT%H%M%S')
        dtend = event_end.strftime('%Y%m%dT%H%M%S')
        dtstamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

        component = f" ({meeting['component']})" if meeting['component'] else ""
        summary = escape_ics_text(f"{course}{component}")
        location = escape_ics_text(meeting['location'])

        events.extend([
            "BEGIN:VEVENT",
            f"DTSTART;TZID=Asia/Singapore:{dtstart}",
            f"DTEND;TZID=Asia/Singapore:{dtend}",
            f"DTSTAMP:{dtstamp}",
            f"UID:{uuid.uuid4()}",
            f"SUMMARY:{summary}",
            f"LOCATION:{location}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])

        current_date += timedelta(days=1)

    return events


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <htm filename>")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found")
        sys.exit(1)

    with open(input_file, 'r', encoding='utf-8') as f:
        html = f.read()

    # Extract course data
    course_names = extract_course_names(html)
    print(f"Found {len(course_names)} courses:")
    for c in course_names:
        print(f"  - {c}")

    # Extract meeting data
    schedules = get_span_values(html, 'MTG_SCHED')
    locations = get_span_values(html, 'MTG_LOC')
    dates = get_span_values(html, 'MTG_DATES')
    components = get_span_values(html, 'MTG_COMP')

    print(f"\nFound {len(schedules)} schedule entries")
    print(f"Found {len(locations)} location entries")
    print(f"Found {len(dates)} date entries")
    print(f"Found {len(components)} component entries")

    # Associate meetings with courses
    course_positions = get_course_positions(html)
    meeting_positions = get_meeting_positions(html)
    meetings_by_course = associate_meetings_with_courses(
        course_positions, meeting_positions, locations, dates, components
    )

    print("\n--- Meetings by course ---")
    for course, meetings in meetings_by_course.items():
        print(f"\n{course}: {len(meetings)} meetings")

    # Generate and save ICS
    ics_content = generate_ics(meetings_by_course)
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    output_path = f"{base_name}.ics"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ics_content)

    print(f"\nICS file saved to: {output_path}")

    # Preview first few events
    print("\n--- Preview of first few events ---")
    for line in ics_content.split('\n')[:50]:
        print(line)


if __name__ == "__main__":
    main()
