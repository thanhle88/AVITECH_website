import os
import re
from pathlib import Path
from difflib import SequenceMatcher

# ============================================================================
# SPECIAL CASES: Manual duplicate mappings
# ============================================================================
# Format: 'duplicate_key': 'keep_key'
# The duplicate will be removed, and only the keep_key will be retained
MANUAL_DUPLICATES = {
    'Son2025TTCT2C': 'nl.trung2022:book:TWR',  # incollection is a chapter of the book
}

# ============================================================================
# FILTERING SETTINGS
# ============================================================================
MIN_YEAR = 2017  # Only keep publications from this year onwards

# ============================================================================

def parse_bib_file(file_path):
    """Parse a .bib file and extract all entries."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all BibTeX entries
    entries = []
    pattern = r'@(\w+)\{([^,]+),\s*(.*?)\n\}'
    matches = re.finditer(pattern, content, re.DOTALL | re.MULTILINE)

    for match in matches:
        entry_type = match.group(1)
        entry_key = match.group(2)
        entry_body = match.group(3)

        # Parse fields
        fields = {}
        field_pattern = r'(\w+)\s*=\s*\{([^}]*)\}|(\w+)\s*=\s*"([^"]*)"'
        field_matches = re.finditer(field_pattern, entry_body)

        for field_match in field_matches:
            if field_match.group(1):
                field_name = field_match.group(1).lower()
                field_value = field_match.group(2)
            else:
                field_name = field_match.group(3).lower()
                field_value = field_match.group(4)
            fields[field_name] = field_value

        entries.append({
            'type': entry_type,
            'key': entry_key,
            'fields': fields,
            'raw': match.group(0)
        })

    return entries

def normalize_text(text):
    """Normalize text for comparison by converting to lowercase and removing extra spaces."""
    if not text:
        return ""
    # Remove special LaTeX characters and normalize
    text = re.sub(r'[\\{}]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def calculate_similarity(str1, str2):
    """Calculate similarity ratio between two strings."""
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, normalize_text(str1), normalize_text(str2)).ratio()

def get_venue_field(entry):
    """Get the appropriate venue field based on entry type."""
    entry_type = entry['type'].lower()
    fields = entry['fields']

    # Map entry types to their venue fields
    if entry_type == 'article':
        return fields.get('journal', '')
    elif entry_type in ['inproceedings', 'conference']:
        return fields.get('booktitle', '')
    elif entry_type == 'book':
        return fields.get('publisher', '') or fields.get('series', '')
    elif entry_type == 'incollection':
        return fields.get('booktitle', '')
    elif entry_type in ['misc', 'preprint']:
        return fields.get('journal', '') or fields.get('howpublished', '') or fields.get('note', '')
    elif entry_type == 'thesis' or entry_type == 'phdthesis' or entry_type == 'mastersthesis':
        return fields.get('school', '')
    elif entry_type == 'techreport':
        return fields.get('institution', '')
    else:
        # Default: try journal, booktitle, or publisher
        return fields.get('journal', '') or fields.get('booktitle', '') or fields.get('publisher', '')

def is_incollection_of_book(incollection, book):
    """Check if an incollection entry is a chapter of a book entry."""
    if incollection['type'].lower() != 'incollection' or book['type'].lower() != 'book':
        return False

    # Check if they have similar authors and same year
    author_sim = calculate_similarity(
        incollection['fields'].get('author', ''),
        book['fields'].get('author', '') or book['fields'].get('editor', '')
    )

    incollection_year = incollection['fields'].get('year', '')
    book_year = book['fields'].get('year', '')
    same_year = incollection_year == book_year if incollection_year and book_year else False

    # If same authors and same year, likely related
    if author_sim > 0.7 and same_year:
        return True

    # Check if the booktitle of incollection contains keywords from book title
    # This works even if one is in English and one is in Vietnamese
    incollection_booktitle = normalize_text(incollection['fields'].get('booktitle', ''))
    book_title = normalize_text(book['fields'].get('title', ''))

    if not incollection_booktitle or not book_title:
        return False

    # Extract significant words (longer than 3 chars) from book title
    book_words = [w for w in book_title.split() if len(w) > 3]

    # Check if at least 2 significant words from book title appear in incollection booktitle
    matching_words = sum(1 for word in book_words if word in incollection_booktitle)

    if len(book_words) > 0 and matching_words >= min(2, len(book_words)):
        return True

    # Fallback: High similarity (>80%) means the incollection is likely a chapter of the book
    similarity = calculate_similarity(incollection_booktitle, book_title)
    return similarity > 0.8

def are_entries_duplicate(entry1, entry2, threshold=0.7):
    """Check if two entries are duplicates based on author, journal/booktitle, and title."""

    # Special case: book and incollection relationship
    # If incollection is a chapter of book, consider incollection as duplicate (keep book only)
    if (entry1['type'].lower() == 'book' and entry2['type'].lower() == 'incollection'):
        if is_incollection_of_book(entry2, entry1):
            return True  # incollection is duplicate of book
    elif (entry1['type'].lower() == 'incollection' and entry2['type'].lower() == 'book'):
        if is_incollection_of_book(entry1, entry2):
            return True  # incollection is duplicate of book

    # Get venue using appropriate field for each entry type
    venue1 = get_venue_field(entry1)
    venue2 = get_venue_field(entry2)

    # Calculate similarities
    author_sim = calculate_similarity(
        entry1['fields'].get('author', ''),
        entry2['fields'].get('author', '')
    )

    title_sim = calculate_similarity(
        entry1['fields'].get('title', ''),
        entry2['fields'].get('title', '')
    )

    venue_sim = calculate_similarity(venue1, venue2)

    # Average similarity across all three fields
    avg_similarity = (author_sim + title_sim + venue_sim) / 3

    return avg_similarity >= threshold

def merge_bib_files(bibs_dir, output_file, similarity_threshold=0.7):
    """Merge all .bib files from bibs_dir, removing duplicates."""
    bibs_path = Path(bibs_dir)

    if not bibs_path.exists():
        print(f"Error: Directory {bibs_dir} does not exist")
        return

    # Collect all .bib files
    bib_files = sorted(bibs_path.glob('*.bib'))

    if not bib_files:
        print(f"No .bib files found in {bibs_dir}")
        return

    print(f"Found {len(bib_files)} .bib files")

    # Collect all entries first
    all_entries = []

    # Process each file
    for bib_file in bib_files:
        print(f"Processing {bib_file.name}...")
        entries = parse_bib_file(bib_file)
        all_entries.extend(entries)

    total_count = len(all_entries)

    # Sort entries: prioritize @book over @incollection for same publications
    # This ensures that when we detect book-incollection relationship, we keep the book
    def entry_priority(entry):
        entry_type = entry['type'].lower()
        if entry_type == 'book':
            return 0  # Highest priority
        elif entry_type == 'incollection':
            return 2  # Lower priority
        else:
            return 1  # Medium priority

    all_entries.sort(key=entry_priority)

    # Now deduplicate
    unique_entries = []
    duplicate_count = 0
    filtered_count = 0
    filtered_incomplete = 0
    filtered_no_year = 0

    for entry in all_entries:
        # Filter entries without year field (required)
        year_str = entry['fields'].get('year', '')
        if not year_str:
            filtered_no_year += 1
            print(f"  Filtered (no year): {entry['key']}")
            continue

        # Filter incomplete @misc entries (no useful publication info)
        if entry['type'].lower() == 'misc':
            has_venue = bool(entry['fields'].get('journal') or
                           entry['fields'].get('booktitle') or
                           entry['fields'].get('publisher') or
                           entry['fields'].get('howpublished'))
            has_doi = bool(entry['fields'].get('doi'))
            has_url = bool(entry['fields'].get('url'))

            # If @misc has no venue, no doi, and only has citation field, filter it out
            if not has_venue and not has_doi:
                # Check if it only has author, title, citation, note
                if 'citation' in entry['fields'] or 'note' in entry['fields']:
                    filtered_incomplete += 1
                    print(f"  Filtered (incomplete @misc): {entry['key']}")
                    continue

        # Filter by year
        try:
            year = int(year_str)
            if year < MIN_YEAR:
                filtered_count += 1
                print(f"  Filtered (year {year}): {entry['key']}")
                continue
        except ValueError:
            # If year is not a valid integer, filter it out
            filtered_no_year += 1
            print(f"  Filtered (invalid year '{year_str}'): {entry['key']}")
            continue

        # Check manual duplicates first
        if entry['key'] in MANUAL_DUPLICATES:
            duplicate_count += 1
            print(f"  Manual duplicate: {entry['key']} ~ {MANUAL_DUPLICATES[entry['key']]}")
            continue

        # Check if this entry is a duplicate
        is_duplicate = False

        for unique_entry in unique_entries:
            if are_entries_duplicate(entry, unique_entry, similarity_threshold):
                is_duplicate = True
                duplicate_count += 1
                print(f"  Duplicate found: {entry['key']} ~ {unique_entry['key']}")
                break

        if not is_duplicate:
            unique_entries.append(entry)    # Write merged output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("% Merged AVITECH Publications\n")
        f.write(f"% Total entries: {len(unique_entries)}\n")
        f.write(f"% Duplicates removed: {duplicate_count}\n")
        f.write(f"% Filtered by year (< {MIN_YEAR}): {filtered_count}\n")
        f.write(f"% Filtered incomplete @misc: {filtered_incomplete}\n")
        f.write(f"% Filtered no/invalid year: {filtered_no_year}\n")
        f.write(f"% Original total: {total_count}\n\n")

        for entry in unique_entries:
            f.write(entry['raw'])
            f.write('\n\n')

    print(f"\nMerge complete!")
    print(f"Total entries processed: {total_count}")
    print(f"Unique entries: {len(unique_entries)}")
    print(f"Duplicates removed: {duplicate_count}")
    print(f"Filtered by year (< {MIN_YEAR}): {filtered_count}")
    print(f"Filtered incomplete @misc: {filtered_incomplete}")
    print(f"Filtered no/invalid year: {filtered_no_year}")
    print(f"Output written to: {output_file}")

if __name__ == "__main__":
    # Get the script directory
    script_dir = Path(__file__).parent

    # Navigate to repository root (assuming scripts/publications structure)
    repo_root = script_dir.parent.parent

    bibs_directory = repo_root / "bibs"
    output_file = script_dir / "AVITECH.bib"  # Output in same directory as script

    # Run the merge with 70% similarity threshold
    merge_bib_files(bibs_directory, output_file, similarity_threshold=0.7)
