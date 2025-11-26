import os
import re
from pathlib import Path
from difflib import SequenceMatcher

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

def are_entries_duplicate(entry1, entry2, threshold=0.7):
    """Check if two entries are duplicates based on author, journal/booktitle, and title."""
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
    
    # Store unique entries
    unique_entries = []
    duplicate_count = 0
    total_count = 0
    
    # Process each file
    for bib_file in bib_files:
        print(f"Processing {bib_file.name}...")
        entries = parse_bib_file(bib_file)
        total_count += len(entries)
        
        for entry in entries:
            # Check if this entry is a duplicate
            is_duplicate = False
            
            for unique_entry in unique_entries:
                if are_entries_duplicate(entry, unique_entry, similarity_threshold):
                    is_duplicate = True
                    duplicate_count += 1
                    print(f"  Duplicate found: {entry['key']} ~ {unique_entry['key']}")
                    break
            
            if not is_duplicate:
                unique_entries.append(entry)
    
    # Write merged output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("% Merged AVITECH Publications\n")
        f.write(f"% Total entries: {len(unique_entries)}\n")
        f.write(f"% Duplicates removed: {duplicate_count}\n")
        f.write(f"% Original total: {total_count}\n\n")
        
        for entry in unique_entries:
            f.write(entry['raw'])
            f.write('\n\n')
    
    print(f"\nMerge complete!")
    print(f"Total entries processed: {total_count}")
    print(f"Unique entries: {len(unique_entries)}")
    print(f"Duplicates removed: {duplicate_count}")
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
