from flask import Flask, render_template, request
import requests
import utm
import numpy as np
from bs4 import BeautifulSoup
import folium
from scipy.interpolate import RBFInterpolator
import re

app = Flask(__name__)

def generate_precalibrated_matrix(easting_northing_matrix):
    """
    Applies calibration adjustments to the easting and northing coordinates using interpolation.

    Args:
        easting_northing_matrix (list of lists or numpy array): 
            A matrix where each row is [easting, northing].

    Returns:
        numpy.ndarray: Precalibrated easting and northing matrix.
    """

    # Convert input to numpy array
    easting_northing_matrix = np.array(easting_northing_matrix)
    
    if easting_northing_matrix.shape[1] != 2:
        raise ValueError("Input matrix must have exactly two columns: [easting, northing]")

    # Extract eastings and northings
    eastings = easting_northing_matrix[:, 0]
    northings = easting_northing_matrix[:, 1]

    # Calibration reference points
    given_easting = np.array([477504.6975, 482977.07875, 487741.8536])
    given_northing = np.array([980922.813, 992734.94275, 993586.1784])
    easting_calib_req = np.array([90.6484, 92.6484, 94.6484])
    northing_calib_req = np.array([204.2779, 210.2779, 208.2779])

    # Compute mean values for interpolation
    this_mean_easting = np.mean(eastings)
    this_mean_northing = np.mean(northings)

    # Combine given_easting and given_northing as input data points
    points = np.column_stack((given_easting, given_northing))

    # Use RBFInterpolator for interpolation & extrapolation
    F_easting_calib_req = RBFInterpolator(points, easting_calib_req, smoothing=0)
    F_northing_calib_req = RBFInterpolator(points, northing_calib_req, smoothing=0)

    # Compute calibration values
    calib_value_eastings = F_easting_calib_req([[this_mean_easting, this_mean_northing]])[0]
    calib_value_northings = F_northing_calib_req([[this_mean_easting, this_mean_northing]])[0]


    # Print computed calibration values
    #print(f"Mean Easting: {this_mean_easting}, Mean Northing: {this_mean_northing}")
    #print(f"Calibration Value for Eastings: {calib_value_eastings}")
    #print(f"Calibration Value for Northings: {calib_value_northings}")

    # Apply calibration
    precalib_eastings = eastings + calib_value_eastings
    precalib_northings = northings + calib_value_northings

    # Return the precalibrated matrix
    return np.column_stack((precalib_eastings, precalib_northings))

def extract_coordinates_from_addisland(title_deed_number):
    """
    Scrapes the Addis Land website and extracts the Easting/Northing coordinates.
    """

    url = f"https://www.addisland.gov.et/en-us/certificate/{title_deed_number}"
    print(f"🔍 Checking URL: {url}")  # Debug print

    try:
        response = requests.get(url)
        response.raise_for_status()  # Will raise an error for bad responses (4xx, 5xx)
        print("✅ Successfully fetched HTML")
        #print(response.text[:1000])  # Print the first 1000 characters of the page
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to fetch HTML: {e}")
        return None


    try:
        soup = BeautifulSoup(response.text, "html.parser")

        # Save the prettified HTML to a text file with utf-8 encoding
        #with open('temp_html_output.txt', 'w', encoding='utf-8') as file:
        #    file.write(soup.prettify())

        tables = soup.find_all("table")

        selected_table = None
 
        print(f"🔍 Found {len(tables)} tables.")
        for i, table in enumerate(tables):
            spans = table.find_all("span")
            span_texts = [span.get_text(strip=True) for span in spans]
            #print(f"📌 Table {i}: {span_texts}")  # Print table contents

            if any("Cordnates/" in text for text in span_texts):
                print("✅ Found the correct table!")
                selected_table = table
                break

        rows = selected_table.find_all("tr")
        coordinate_data = []

        for row in rows[1:]:  # Skip header row
            cols = row.find_all("td")
            if len(cols) == 2:
                x = cols[0].get_text(strip=True)
                y = cols[1].get_text(strip=True)

                # Ensure extracted values are numeric before conversion
                if x.replace(".", "", 1).isdigit() and y.replace(".", "", 1).isdigit():
                    coordinate_data.append([float(x), float(y)])
                else:
                    pass
                    #print(f"⚠️ Skipping non-numeric row: {x}, {y}")

        if not coordinate_data:
            print("❌ No valid coordinates found")
            return None
        
        # Regular Expression to Find the PDF Export Link
        pdf_pattern = re.compile(r"https:\/\/www\.addisland\.gov\.et\/Reserved\.ReportViewerWebControl\.axd\?[^\"\']*Format=PDF")

        # Extract All Matching PDF Links
        # Find the link (using regex if necessary)
        save_as_pdf_link = soup.find('a', href=pdf_pattern)

        print(f"📌 Found Save AS PDF Link {i}: {save_as_pdf_link}")

        if coordinate_data:
            return coordinate_data,save_as_pdf_link
        else:
            return None, None

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None, None



def convert_and_plot(easting_northing_matrix, title="Land Plot"):
    """
    Converts Easting/Northing to Lat/Lon, embeds the Folium map.
    """
    if not easting_northing_matrix:
        return None
    
    # Determine UTM zone (default 37 for Addis Ababa)
    zone = 37
    computed_lats, computed_lons = [], []
    
    eastings = np.array(easting_northing_matrix)[:, 0]
    northings = np.array(easting_northing_matrix)[:, 1]

    # Calibration values for correcting positions
    precalib_easting_northing_matrix = generate_precalibrated_matrix(easting_northing_matrix)
    
    for easting, northing in precalib_easting_northing_matrix:
        lat, lon = utm.to_latlon(easting, northing, zone, northern=True)
        computed_lats.append(lat)
        computed_lons.append(lon)

    # Close the plot shape
    computed_lats.append(computed_lats[0])
    computed_lons.append(computed_lons[0])

    center_lat, center_lon = np.mean(computed_lats), np.mean(computed_lons)
    # ESRI World Imagery (Best Alternative to Google Satellite)
    map_ESRI_World_Imagery = folium.Map(location=[center_lat, center_lon], zoom_start=18, max_zoom=109, tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Tiles © Esri &mdash; Source: Esri, Maxar, Earthstar Geographics")
    # Stamen Terrain (For a Topographic View)
    map_Stamen_Terrain = folium.Map(location=[center_lat, center_lon], zoom_start=18, max_zoom=109, tiles="https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg", attr="Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.")

    map_ = map_ESRI_World_Imagery
    #map_ = map_Stamen_Terrain

    
    # Add markers
    for lat, lon in zip(computed_lats[:-1], computed_lons[:-1]):
        folium.Marker([lat, lon], popup="Point").add_to(map_)

    # Draw boundary
    folium.PolyLine(list(zip(computed_lats, computed_lons)), color="blue", weight=2.5, opacity=1).add_to(map_)

    return map_._repr_html_()  # Return HTML for embedding






@app.route("/", methods=["GET", "POST"])  # Ensure POST is allowed
def index():
    map_html = None
    title_deed_number = ""
    save_as_pdf_link = None
    
    if request.method == "POST":  # Handle form submission
        title_deed_number = request.form.get("title_deed", "").strip()

        if title_deed_number:
            easting_northing_matrix,save_as_pdf_link = extract_coordinates_from_addisland(title_deed_number)
            if easting_northing_matrix:
                map_html = convert_and_plot(easting_northing_matrix, title=title_deed_number)
                print("✅ Plot the coordinates over Folium map!")
            else:
                map_html = "<p style='color:red;'>Failed to retrieve coordinates.</p>"

    return render_template("index.html", map_html=map_html, title_deed_number=title_deed_number, save_as_pdf_link = save_as_pdf_link)

# 🚀 NEW ROUTE: Extract PDF Export Link
@app.route("/extract_pdf_links")
def extract_pdf_links():
    target_url = "https://www.addisland.gov.et/YOUR_PAGE_CONTAINING_LINKS"

    try:
        response = requests.get(target_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Regular Expression to Find the PDF Export Link
        pdf_pattern = re.compile(r"https:\/\/www\.addisland\.gov\.et\/Reserved\.ReportViewerWebControl\.axd\?[^\"\']*Format=PDF")

        # Extract All Matching PDF Links
        pdf_links = [a["href"] for a in soup.find_all("a", href=True) if pdf_pattern.search(a["href"])]

        return jsonify({"pdf_links": pdf_links}), 200 if pdf_links else (jsonify({"error": "No PDF export links found."}), 404)

    except requests.RequestException as e:
        return jsonify({"error": f"Failed to fetch page: {str(e)}"}), 500
    

if __name__ == "__main__":
    app.run(debug=True)
