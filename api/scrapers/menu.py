
import httpx
from bs4 import BeautifulSoup
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / 'config.json'

def get_menu_url(locale: str = 'el'):
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config.get("menu_urls", {}).get(locale)

def extract_meal_section(menu_text: str, meal_name: str):
    lines = menu_text.split('\n')
    meal_start_index = -1
    meal_end_index = len(lines)
    breakfast_headers = ['Πρωινό', 'Breakfast']
    lunch_headers = ['Μεσημεριανό', 'Lunch']
    dinner_headers = ['Βραδινό', 'Dinner']
    current_meal_headers = []
    next_meal_headers = []
    if meal_name == 'breakfast':
        current_meal_headers = breakfast_headers
        next_meal_headers = lunch_headers
    elif meal_name == 'lunch':
        current_meal_headers = lunch_headers
        next_meal_headers = dinner_headers
    elif meal_name == 'dinner':
        current_meal_headers = dinner_headers
        next_meal_headers = []
    for i, line in enumerate(lines):
        line = line.strip()
        if any(line == header for header in current_meal_headers):
            meal_start_index = i
        if meal_start_index != -1 and next_meal_headers and any(line == header for header in next_meal_headers):
            meal_end_index = i
            break
    if meal_start_index != -1:
        meal_lines = lines[meal_start_index:meal_end_index]
        return '\n'.join(meal_lines)
    return ''

def format_menu_text(text: str, skip_first_lines: bool = True):
    if not text:
        return ''
    text = text.replace('*', '')
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    formatted_html = ''
    in_breakfast_section = False
    breakfast_content = []

    # Inline style definitions
    styles = {
        'menu-date': 'font-size:1.25rem;color:var(--ion-color-primary);font-weight:500;text-align:center;margin:0;',
        'meal-header': 'font-size:1.5rem;font-weight:bold;color:var(--ion-color-primary);margin-bottom:0.5rem;border-bottom:2px solid var(--ion-color-primary);',
        'meal-time': 'font-size:0.9rem;color:var(--ion-color-medium);font-style:italic;margin-bottom:1rem;',
        'category-header': 'font-size:1.1rem;font-weight:600;color:var(--ion-color-primary);margin-top:1rem;margin-bottom:0.5rem;text-transform:uppercase;',
        'selection-note': 'font-size:0.9rem;color:var(--ion-color-medium);margin-bottom:0.25rem;',
        'menu-item': 'font-size:1rem;margin-bottom:0.5rem;margin-top:0.5rem;line-height:1.5;padding-left:0.5rem;',
        'breakfast-content': 'font-size:0.95rem;line-height:1.6;margin-bottom:0.5rem;padding-left:0.5rem;'
    }

    for i, line in enumerate(lines):
        if i == 0 and skip_first_lines:
            continue
        if skip_first_lines and i <= 3:
            date_match = __import__('re').search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
            if date_match:
                formatted_html += f'<p style="{styles["menu-date"]}">📅 {date_match.group(1)}</p>'
                continue
            if __import__('re').match(r'^(Πρόγραμμα Συσσιτίου|Date of Menu|:)$', line, __import__('re').IGNORECASE):
                continue
        if __import__('re').match(r'^(Πρωινό|Μεσημεριανό|Βραδινό|Breakfast|Lunch|Dinner)$', line):
            if in_breakfast_section and breakfast_content:
                formatted_html += f'<p style="{styles["menu-item"]}{styles["breakfast-content"]}">{" ".join(breakfast_content)}</p>'
                breakfast_content = []
            formatted_html += f'<h2 style="{styles["meal-header"]}">{line}</h2>'
            in_breakfast_section = line in ['Πρωινό', 'Breakfast']
        elif __import__('re').search(r'\(.*?\d{2}:\d{2}.*?\)', line):
            if in_breakfast_section and breakfast_content:
                formatted_html += f'<p style="{styles["menu-item"]}{styles["breakfast-content"]}">{" ".join(breakfast_content)}</p>'
                breakfast_content = []
            formatted_html += f'<p style="{styles["meal-time"]}">{line}</p>'
        elif __import__('re').match(r'^[A-ZΑ-Ω\s]+$', line) and len(line) < 50:
            if in_breakfast_section and breakfast_content:
                formatted_html += f'<p style="{styles["menu-item"]}{styles["breakfast-content"]}">{" ".join(breakfast_content)}</p>'
                breakfast_content = []
            formatted_html += f'<h3 style="{styles["category-header"]}">{line}</h3>'
            in_breakfast_section = False
        elif __import__('re').search(r'επιλογή από|selection from', line, __import__('re').IGNORECASE):
            formatted_html += f'<p style="{styles["selection-note"]}"><em>{line}</em></p>'
        elif __import__('re').match(r'^[\(\)]+$', line):
            continue
        else:
            if in_breakfast_section:
                breakfast_content.append(line)
            else:
                formatted_html += f'<p style="{styles["menu-item"]}">{line}</p>'
    if breakfast_content:
        formatted_html += f'<p style="{styles["menu-item"]}{styles["breakfast-content"]}">{" ".join(breakfast_content)}</p>'
    return formatted_html

async def scrape_menu_data(locale: str = 'el'):
    menu_link = get_menu_url(locale)
    if not menu_link:
        return {"error": f"menu_url for locale {locale} not found in config.json"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(menu_link)
            response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the menu accordion by locating the day names (Δευτέρα/Monday)
        day_markers = ['Δευτέρα', 'Monday']
        menu_accordion = None
        for marker in day_markers:
            day_element = soup.find(string=lambda t: t and t.strip() == marker)
            if day_element:
                # Navigate up to find the e-n-accordion container
                parent = day_element
                while parent:
                    if hasattr(parent, 'get') and 'e-n-accordion' in (parent.get('class') or []):
                        menu_accordion = parent
                        break
                    parent = parent.parent
                if menu_accordion:
                    break
        
        if not menu_accordion:
            return {"error": "Could not find menu accordion on page"}
        
        # Get accordion items only from the menu section
        days = menu_accordion.select('.e-n-accordion-item')
        parsed_days = []
        for day in days:
            text = day.get_text(separator='\n', strip=True)
            day_obj = {
                "full": format_menu_text(text, skip_first_lines=True),
                "breakfast": format_menu_text(extract_meal_section(text, 'breakfast'), skip_first_lines=False),
                "lunch": format_menu_text(extract_meal_section(text, 'lunch'), skip_first_lines=False),
                "dinner": format_menu_text(extract_meal_section(text, 'dinner'), skip_first_lines=False)
            }
            parsed_days.append(day_obj)
        return {"days": parsed_days}
    except httpx.HTTPStatusError as e:
        print(f"Error while scraping data: {e}")
        return {"error": "Error while scraping data"}
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": "An unexpected error occurred"}
