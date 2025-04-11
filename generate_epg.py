import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import logging
import sys
import os # Needed for output file path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_URL = "https://data-store-trans-cdn.api.cms.amdvids.com/live/epg/US/website"
# Output file will be in the root of the repository/workspace
OUTPUT_FILE = os.path.join(os.getcwd(), "epg.xml")
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/91.0.4472.124 Safari/537.36' # Using a reasonably modern Chrome UA
)

def unix_to_xmltv(timestamp):
    """Converts a Unix timestamp (seconds since epoch) to XMLTV UTC format."""
    try:
        # Assume timestamp is integer seconds; handle potential float/string input
        dt_object = datetime.utcfromtimestamp(int(float(timestamp)))
        return dt_object.strftime('%Y%m%d%H%M%S') + " +0000"
    except (ValueError, TypeError, OverflowError) as e:
        logging.error(f"Error converting timestamp '{timestamp}': {e}")
        return None # Indicate failure

def create_xmltv(data):
    """Creates an XMLTV ElementTree object from the fetched JSON data."""
    if not isinstance(data, dict) or "channels" not in data or not isinstance(data["channels"], list):
        logging.error("Invalid data structure received from API: 'channels' key missing or not a list.")
        return None

    tv = ET.Element("tv")
    # Add generator info attribute (optional but good practice for XMLTV)
    tv.set("generator-info-name", "GitHub Actions EPG Generator")
    tv.set("generator-info-url", "https://github.com/features/actions")

    channel_count = 0
    program_count = 0

    for channel in data["channels"]:
        if not isinstance(channel, dict) or "_id" not in channel or "name" not in channel:
            logging.warning(f"Skipping invalid channel entry: {channel}")
            continue

        channel_id = str(channel["_id"]) # Ensure ID is string
        channel_name = channel.get("name", "Unknown Channel") # Default if name is missing

        channel_elem = ET.SubElement(tv, "channel", id=channel_id)
        ET.SubElement(channel_elem, "display-name").text = channel_name
        # You could add <icon src="..."/> here if channel icons are available in the data
        channel_count += 1

        programs = channel.get("program", [])
        if not isinstance(programs, list):
            logging.warning(f"Channel '{channel_name}' ({channel_id}) has invalid 'program' data type. Skipping programs.")
            continue

        for program in programs:
            if not isinstance(program, dict):
                logging.warning(f"Skipping invalid program entry for channel '{channel_name}' ({channel_id}): {program}")
                continue

            # Check essential program keys
            start_ts = program.get("starts_at")
            end_ts = program.get("ends_at")
            title = program.get("program_title")

            if start_ts is None or end_ts is None or title is None:
                logging.warning(f"Skipping program with missing essential data for channel '{channel_name}' ({channel_id}): {program}")
                continue

            start_xmltv = unix_to_xmltv(start_ts)
            stop_xmltv = unix_to_xmltv(end_ts)

            if start_xmltv is None or stop_xmltv is None:
                logging.warning(f"Skipping program due to timestamp conversion error for channel '{channel_name}' ({channel_id}): {program}")
                continue

            # Basic sanity check: start time should be before end time
            if start_ts >= end_ts:
                 logging.warning(f"Skipping program with start time >= end time for channel '{channel_name}' ({channel_id}): {program}")
                 continue

            prog_elem = ET.SubElement(
                tv,
                "programme",
                start=start_xmltv,
                stop=stop_xmltv,
                channel=channel_id
            )
            ET.SubElement(prog_elem, "title", lang="en").text = str(title)

            # Add description if available and not empty
            description = program.get("program_description")
            if description and str(description).strip():
                ET.SubElement(prog_elem, "desc", lang="en").text = str(description)

            # Add other potential fields if needed (e.g., category, episode-num)
            # episode_num = program.get("episode_number")
            # if episode_num:
            #    ET.SubElement(prog_elem, "episode-num", system="onscreen").text = str(episode_num)

            program_count += 1

    logging.info(f"Processed {channel_count} channels and {program_count} programs.")
    if channel_count == 0:
        logging.warning("No valid channels were processed. Output XML might lack channel definitions.")
    if program_count == 0:
        logging.warning("No valid programs were processed. Output XML might lack program details.")

    return ET.ElementTree(tv)

def save_xmltv_file(filename, xml_tree):
    """Saves the XMLTV ElementTree to a file."""
    try:
        # Use indent for basic pretty printing (optional but readable)
        ET.indent(xml_tree, space="  ", level=0)
        xml_tree.write(filename, encoding='UTF-8', xml_declaration=True)
        logging.info(f"Successfully wrote XMLTV data to {filename}")
    except IOError as e:
        logging.error(f"Error writing XML file '{filename}': {e}")
        sys.exit(1) # Exit if we can't write the file
    except Exception as e:
        logging.error(f"An unexpected error occurred during XML writing: {e}")
        sys.exit(1)


def main():
    """Main function to fetch data, convert, and save."""
    headers = {
        'User-Agent': USER_AGENT
    }

    logging.info(f"Fetching EPG data from {API_URL}")
    try:
        response = requests.get(API_URL, headers=headers, timeout=45) # Increased timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch EPG data: {e}")
        sys.exit(1) # Exit if fetching fails

    logging.info(f"Successfully fetched EPG data (Status: {response.status_code})")

    try:
        data = response.json()
    except ValueError as e: # Specific exception for JSON decoding
        logging.error(f"Error decoding EPG JSON response: {e}")
        # Log beginning of response text for debugging, careful with potentially large responses
        logging.debug(f"Response text (first 500 chars): {response.text[:500]}...")
        sys.exit(1)

    xmltv_tree = create_xmltv(data)

    if xmltv_tree:
        save_xmltv_file(OUTPUT_FILE, xmltv_tree)
    else:
        logging.error("XMLTV Tree creation failed. No output file generated.")
        sys.exit(1)

if __name__ == "__main__":
    main()
