#!usr/bin/env

import networkx as nx
import pandas as pd
import osmnx as ox
from dash import Dash
import json
import dash_html_components as html
import dash_core_components as dcc
import dash_leaflet as dl
import plotly.express as px
import requests
import dash_leaflet.express as dlx
from dash_extensions.javascript import arrow_function
from dash.dependencies import Output, Input, State
from dash_extensions.javascript import assign
from math import pi,sqrt,sin,cos,atan2
import folium

# 1. read data
df1 = pd.read_csv(r"dataset/somerville_trip.csv")
k1 = pd.read_csv(r"dataset/station_with_ox.csv")
def haversine(pos1, pos2): #pos1 is[lat, lon]
    lat1 = float(pos1[0])
    long1 = float(pos1[1])
    lat2 = float(pos2[0])
    long2 = float(pos2[1])

    degree_to_rad = float(pi / 180.0)

    d_lat = (lat2 - lat1) * degree_to_rad
    d_long = (long2 - long1) * degree_to_rad

    a = pow(sin(d_lat / 2), 2) + cos(lat1 * degree_to_rad) * cos(lat2 * degree_to_rad) * pow(sin(d_long / 2), 2)
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    km = 6367 * c
    mi = 3956 * c

    return {"km":km, "miles":mi}


# Create marker cluster.
dicts = [dict(value = m["station_id"],name=m["station_id"], lat=m["Latitude"], lon=m["Longitude"]) for _, m in k1.iterrows()]
dd_defaults = [o["value"] for o in dicts]
# Create javascript function that filters on feature name.
geojson_filter = assign("function(feature, context){return context.props.hideout != feature.properties.name;}")
cluster = dl.GeoJSON(id="markers", data=dlx.dicts_to_geojson(dicts), options = dict(filter = geojson_filter),
                     hideout = dd_defaults, cluster=True, zoomToBoundsOnClick=True,
                    children=[dl.Tooltip(id="tooltip")])
                     
# Create app.
app = Dash(prevent_initial_callbacks=True)
app.layout = html.Div(children = [
                          html.H1("Bluebike App"),
                          html.Div(
                                    className="div-for-dropdown",
                                    children=[
                                        # Dropdown to select times
                                        dcc.Dropdown(
                                            id="bar-selector",
                                            options=[
                                                {
                                                    "label": m["station_id"],
                                                    "value": m["station_id"],
                                                }
                                                for _, m in k1.iterrows()
                                            ],
                                            multi=True,
                                            placeholder="select station",
                                        )]),
                      html.Div(["radius(meter): ",dcc.Input(id='radius-input', value='500', type='text')]),
                      html.Div(dl.Map([dl.TileLayer(), cluster, dl.LayerGroup(id="container", children=[]),
                                      dl.LayerGroup(id = "selected_marker", children = [])],
                                      zoom= 10, center=(42.3848, -71.0951)),
                      style={'width': '100%', 'height': '70vh', 'margin': "auto", "display": "block"}),
                      html.Div(id = "all_stations_in_radius"),
                      html.H5("shortest route between stations"),
                      dcc.Dropdown(id="from_selector",
                              options=[{
                                        "label": m["station_id"],
                                        "value": m["station_id"],
                                        } for _, m in k1.iterrows()],
                                        multi=False,
                                        placeholder="start station"),
                      dcc.Dropdown(id="to_selector",
                              options=[{
                                        "label": m["station_id"],
                                        "value": m["station_id"],
                                        } for _, m in k1.iterrows()],
                                        multi=False,
                                        placeholder="end station"),
                      html.Iframe(id = "station_distance", 
                                  srcDoc = open("ox_folium/basemap_station.html", "r").read(),
                                 width = "100%", height = "450"),
                      
                      
])


# update the dropdown selector values when the marker is clicked
@app.callback(
    Output("bar-selector", "value"),
    [Input("markers", "click_feature")],
)
def update_bar_selector(feature):
    #holder = []
    #marker_id = dash.callback_context.triggered[0]["prop_id"].split(".")[0]
    #holder.append(marker_id)
    holder = []
    holder.append(feature["properties"]["name"])
    return list(set(holder))


## change marker color when clicked: by adding a another marker at the selected location with different color
app.clientside_callback("function(x){return x;}", Output("markers", "hideout"), Input("bar-selector", "value"))
# add a new CircleMarker here
@app.callback(
    Output("selected_marker", "children"),
    [Input("bar-selector", "value"), State("selected_marker", "children")]
)
def last_selected_marker(station_id, children):
    if not station_id:
        children.clear()
        return children
    station = k1[k1["station_id"] == station_id[0]]
    lat, lon = station.loc[:,"station_lat"].values[0], station.loc[:,"station_lon"].values[0]
    children.clear()
    children.append(dl.Circle(center=[lat, lon], radius=10, color='rgb(0, 0, 255)')) #color red: (255, 0, 0)
    return children



# get marker lonlat and pass it to circle position and make a circle with input radius in meters
@app.callback(
    Output("container", "children"),
    [Input("bar-selector", "value"), Input("radius-input", "value"),State("container", "children")]
)
def plot_radius(val1, val2, children):
    if not val2 or val2 == "0":
        radius = 1000
    else:
        radius = int(val2)
    if not val1:
        children.clear()
        return children
    else:
        tooltip_text = "radius of " + str(radius)
        station = k1[k1["station_id"] == val1[0]]
        lat, lon = station.loc[:,"station_lat"].values[0], station.loc[:,"station_lon"].values[0]
        children.clear()
        children.append(dl.Circle(center=[lat, lon], radius=radius, color='rgb(255,128,0)', children=[
            dl.Tooltip(tooltip_text)]))
        return children
    
## calculate the all stations that is inside the radius, if radius is not selected, default is 1000 meters
@app.callback(
    Output("all_stations_in_radius", "children"),
    [Input("bar-selector", "value"), Input("radius-input", "value")]
)
def station_in_radius(station_id, radius_val):
    if (not station_id) or (not radius_val):
        return "none"
    if int(radius_val) <= 0:
        return "none"
    station = k1[k1["station_id"] == station_id[0]]
    lat, lon = station.loc[:,"station_lat"].values[0], station.loc[:,"station_lon"].values[0]
    select_radius = int(radius_val)
    output_stations = []
    for _, row in k1.iterrows():
        havr = haversine([row["Latitude"], row["Longitude"]], [lat, lon])
        if havr["km"]*1000 <= select_radius:
            output_stations.append((row["station_id"], round(havr["km"]*1000,2)))
    return json.dumps(output_stations)
    
    
# 3. callback to calculate the shortest distance of two stations, and plot them
def get_single_marker(station_id, lat, lon):
    m = folium.Map(location = [lat, lon], zoom_start = 13)
    text_on_marker = station_id
    folium.Marker([lat, lon], tooltip = text_on_marker,icon = folium.Icon(color = "red", icon = "info-sign")).add_to(m)
    filepath = "ox_folium/signle_marker.html"
    m.save(filepath)
    return open(filepath, "r").read()

    
## calculate shortest path between two stations and display them    
@app.callback(
    Output("station_distance", "srcDoc"),
    [Input("from_selector", "value"), Input("to_selector", "value")]
)
def get_shortest_path(val1, val2):
    """
    A shortest path of bike path system, 
        1. some highway are not allowed bike ride
        2. there might be several shortest paths between two nodes
    """
    if val1 and val2:
        from_station = k1[k1["station_id"] == int(val1)].copy().reset_index(drop = True)
        from_lat, from_lon = from_station.loc[:,"station_lat"].values[0], from_station.loc[:,"station_lon"].values[0] 
        to_station = k1[k1["station_id"] == int(val2)].copy().reset_index(drop = True)
        to_lat, to_lon = to_station.loc[:,"station_lat"].values[0], to_station.loc[:,"station_lon"].values[0] 
        if from_lat == to_lat and from_lon == to_lon:
            return get_single_marker(int(val1), to_lat, to_lon)
        graph_path = r"ox_folium/somerville.graphml"
        G = ox.io.load_graphml(graph_path)
        src_ox_id = from_station.loc[:, "ox_nearest_node_id"].values[0]
        dst_ox_id = to_station.loc[:, "ox_nearest_node_id"].values[0]
        route = nx.shortest_path(G, src_ox_id, dst_ox_id)
        
        navigation_map = folium.Map(location = [42.401962, -71.092053], zoom_start=12)
        tooltip_from_id = val1
        tooltip_to_id = val2
        folium.Marker([from_lat, from_lon],tooltip = tooltip_from_id).add_to(navigation_map)
        folium.Marker([to_lat, to_lon], tooltip = tooltip_to_id).add_to(navigation_map)
        shortest_path_map = ox.plot_route_folium(G, route, route_map = navigation_map, popup_attribute = "length", weight = 7)
        shortest_route_html = "ox_folium/shortest_route_graph.html"
        shortest_path_map.save(shortest_route_html)
    
        return open(shortest_route_html, "r").read()
    if (not val1) and (not val2):
        return open("ox_folium/basemap_station.html", "r").read()    
    


## update markers hover feature: show station traffic when hover on it
@app.callback(Output("tooltip", "children"), [Input("markers", "hover_feature")])
def update_tooltip(feature):
    if feature is None:
        return None
    fig = px.histogram(df1[df1["station_id"] == feature["properties"]["name"]], x = "starttime_month",nbins = 12)
    fig.layout.title = feature["properties"]["name"]
    fig.layout.width = 400
    fig.layout.height = 300
    return dcc.Graph(figure=fig)

if __name__ == '__main__':
    app.run_server(debug = False)
