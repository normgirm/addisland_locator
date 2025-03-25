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
        return None, "❌ Server Problem: Failed to get response. Please retry later."


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
        
        ## Regular Expression to Find the PDF Export Link
        #pdf_pattern = re.compile(r"https:\/\/www\.addisland\.gov\.et\/Reserved\.ReportViewerWebControl\.axd\?[^\"\']*Format=PDF")

        ## Extract All Matching PDF Links
        ## Find the link (using regex if necessary)
        #save_as_pdf_link = soup.find('a', href=pdf_pattern)

        #print(f"📌 Found Save AS PDF Link {i}: {save_as_pdf_link}")


        if coordinate_data:
            return {'easting_northing_matrix':coordinate_data,'addisland_url':url}, 'Success'
        else:
            print("❌ No valid coordinates found")
            return None, "❌ No valid coordinates found."

    except Exception as e:
        print(f"Error fetching data: {e}")
        return None, "❌ Invalid Title Deed Number: Please enter correct title deed number."


def convert_eastings_northings_to_lats_lons(easting_northing_matrix):
    """
    Converts Easting/Northing to Lat/Lon, 
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

    return computed_lats,computed_lons


def plot_lats_lons_on_map(computed_lats,computed_lons, title="Land Plot"):
    """
    Takes in Lat/Lon, embeds the Folium map.
    """
    
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
    validity_html = 'Enter Title Deed Number and Click Check'
    google_map_href = 'https://maps.app.goo.gl/jr4S1yaX8NeVXFsa8'
    addisland_href = 'https://www.addisland.gov.et/'

    if request.method == "POST":  # Handle form submission
        title_deed_number = request.form.get("title_deed", "").strip()

        if title_deed_number:
            validity_html = 'Connecting to server ...'
            out_dict, reply_msg = extract_coordinates_from_addisland(title_deed_number)

            if out_dict:
                easting_northing_matrix = out_dict['easting_northing_matrix']
                
                if easting_northing_matrix:
                    computed_lats,computed_lons = convert_eastings_northings_to_lats_lons(easting_northing_matrix)
                    center_lat, center_lon = np.mean(computed_lats), np.mean(computed_lons)
                    google_map_href = f"https://www.google.com/maps?q={center_lat},{center_lon}"
                    addisland_href = out_dict['addisland_url']

                    # Create table rows
                    table_rows = "".join(f"<tr><td>{lat:.8f}</td><td>{lon:.8f}</td></tr>" for lat, lon in zip(computed_lats, computed_lons))

                    # Construct the complete HTML
                    validity_html = f"""
                        <p style='color:green; text-align: center;'>✅ Valid Title Deed: Successfully retrieved coordinates.</p>
                        <p style='color:black; text-align: center;'> Coordinates of {title_deed_number}.</p>
                        <table border='1' style='border-collapse: collapse; width: 50%; margin: auto; text-align: center;'>
                            <tr>
                                <th>Latitude</th>
                                <th>Longitude</th>
                            </tr>
                            {table_rows}
                        </table>
                    """

                    map_html = plot_lats_lons_on_map(computed_lats,computed_lons, title=title_deed_number)
                    
                    #map_html = convert_and_plot(easting_northing_matrix, title=title_deed_number)
                    print("✅ Plot the coordinates over Folium map!")
                else:
                    #map_html = "<p style='color:red;'>Failed to retrieve coordinates.</p>"
                    validity_html = "<p style='color:red;'>❌ Invalid Input: Failed to retrieve coordinates.</p>"
            else:
                validity_html = f"<p style='color:red;'> {reply_msg} .</p>"

    return render_template("index.html", map_html=map_html, validity_html = validity_html, title_deed_number=title_deed_number, google_map_href = google_map_href, addisland_href = addisland_href)

if __name__ == "__main__":
    app.run(debug=True)
