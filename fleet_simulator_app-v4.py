import math
import time
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import folium
from folium.plugins import AntPath
from streamlit_folium import st_folium

# ==============================================================================
# PAGE CONFIGURATION & STYLING
# ==============================================================================
st.set_page_config(
    page_title="Locater 2.0 | Real-Time India Fleet & Delivery Simulator",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern dark/light dashboard theme
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        padding: 15px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .status-active {
        color: #16A34A;
        font-weight: 600;
    }
    .status-rerouted {
        color: #9333EA;
        font-weight: 600;
    }
    .status-delayed {
        color: #DC2626;
        font-weight: 600;
    }
    .status-delivered {
        color: #2563EB;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# GEOGRAPHIC & ROUTE MATHEMATICS (Grounding: DEV Community / StackOverflow)
# ==============================================================================
def calculate_bearing(lat1, lon1, lat2, lon2):
    """Calculates bearing angle in degrees between two coordinates."""
    d_lon = math.radians(lon2 - lon1)
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    
    x = math.sin(d_lon) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(d_lon)
    )
    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360
    return compass_bearing

def interpolate_coordinate(coord1, coord2, fraction):
    """Linear interpolation (lerp) between two GPS points."""
    lat = coord1[0] + (coord2[0] - coord1[0]) * fraction
    lon = coord1[1] + (coord2[1] - coord1[1]) * fraction
    return [lat, lon]

def calculate_haversine_distance(coord1, coord2):
    """Calculates distance in kilometers between two GPS points."""
    R = 6371.0 # Earth radius in kilometers
    lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
    lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==============================================================================
# INDIA BOUNDS & REAL INDIA FLEET ROUTES
# ==============================================================================
# Strict Geographic Bounds for India
INDIA_MIN_LAT, INDIA_MAX_LAT = 6.5, 35.5
INDIA_MIN_LON, INDIA_MAX_LON = 68.0, 97.5

DEFAULT_INDIAN_DEPOTS = {
    "Bengaluru Hub": [12.8452, 77.6602], # Electronic City
    "Mumbai Port Hub": [18.9500, 72.9500], # JNPT / South Mumbai
    "Delhi NCR Hub": [28.6315, 77.2167]   # Connaught Place
}

PREDEFINED_INDIAN_ROUTES = {
    "Vehicle-101 (Bengaluru Tech Express)": {
        "driver": "Rajesh Kumar",
        "type": "Delivery Van",
        "color": "#2563EB", # Blue
        "region": "Bengaluru, KA",
        "capacity_items": 100,
        "cargo_loaded": 85,
        "base_speed_kmh": 40.0,
        "waypoints": [
            [12.8452, 77.6602], # Electronic City Central Depot
            [12.9172, 77.6228], # Silk Board Stop
            [12.9352, 77.6245], # Koramangala Delivery Hub
            [12.9784, 77.6408], # Indiranagar Hub
            [12.9698, 77.7500]  # Whitefield Tech Park Destination
        ]
    },
    "Vehicle-102 (Mumbai Port-BKC Logistics)": {
        "driver": "Priya Sharma",
        "type": "Heavy Truck",
        "color": "#D97706", # Amber
        "region": "Mumbai, MH",
        "capacity_items": 200,
        "cargo_loaded": 180,
        "base_speed_kmh": 35.0,
        "waypoints": [
            [18.9500, 72.9500], # JNPT Cargo Port Depot
            [19.0600, 72.8900], # Chembur Freight Station
            [19.0657, 72.8686], # BKC Financial Center
            [19.0596, 72.8295], # Bandra West Hub
            [19.1197, 72.8464]  # Andheri Cargo Terminal
        ]
    },
    "Vehicle-103 (Delhi NCR Rapid Courier)": {
        "driver": "Amit Patel",
        "type": "Cargo E-Bike",
        "color": "#16A34A", # Green
        "region": "Delhi NCR",
        "capacity_items": 35,
        "cargo_loaded": 30,
        "base_speed_kmh": 28.0,
        "waypoints": [
            [28.6315, 77.2167], # Connaught Place Depot
            [28.6129, 77.2295], # India Gate Transit Point
            [28.5672, 77.2100], # AIIMS / South Ext. Hub
            [28.4950, 77.0895], # Cyber City Gurugram
            [28.5562, 77.1000]  # IGI Airport Freight Hub
        ]
    }
}

TRAFFIC_HAZARD_PRESETS_INDIA = {
    "Silk Board Flyover Congestion (Bengaluru)": {
        "center": [12.9172, 77.6228],
        "radius_km": 1.2,
        "description": "Heavy traffic bottleneck near Outer Ring Road junction."
    },
    "Andheri WEH Waterlogging (Mumbai)": {
        "center": [19.1136, 72.8697],
        "radius_km": 1.0,
        "description": "Western Express Highway road closure and waterlogging."
    },
    "Dhaula Kuan Junction Blockage (Delhi)": {
        "center": [28.5918, 77.1614],
        "radius_km": 1.1,
        "description": "VIP movement and construction delay near Ring Road."
    }
}

# Initialize session state variables
if "fleet_data" not in st.session_state:
    st.session_state.fleet_data = {}
    for v_id, v_info in PREDEFINED_INDIAN_ROUTES.items():
        total_dist = 0.0
        segments = []
        wps = v_info["waypoints"]
        for i in range(len(wps) - 1):
            d = calculate_haversine_distance(wps[i], wps[i+1])
            segments.append(d)
            total_dist += d
            
        st.session_state.fleet_data[v_id] = {
            "driver": v_info["driver"],
            "type": v_info["type"],
            "color": v_info["color"],
            "region": v_info["region"],
            "capacity": v_info["capacity_items"],
            "cargo": v_info["cargo_loaded"],
            "speed": v_info["base_speed_kmh"],
            "waypoints": v_info["waypoints"],
            "original_waypoints": list(v_info["waypoints"]),
            "segment_distances": segments,
            "total_distance": total_dist,
            "progress_pct": 0.0,
            "current_coord": v_info["waypoints"][0],
            "bearing": 0.0,
            "status": "In Transit",
            "rerouted": False,
            "reroute_reason": "",
            "history_speed": [v_info["base_speed_kmh"]],
            "history_time": [0]
        }

if "sim_time" not in st.session_state:
    st.session_state.sim_time = 0
if "speed_multiplier" not in st.session_state:
    st.session_state.speed_multiplier = 1
if "live_loop_active" not in st.session_state:
    st.session_state.live_loop_active = False
if "active_hazards" not in st.session_state:
    st.session_state.active_hazards = {}
if "reroute_events" not in st.session_state:
    st.session_state.reroute_events = []
if "auto_reroute_enabled" not in st.session_state:
    st.session_state.auto_reroute_enabled = True
if "selected_city_view" not in st.session_state:
    st.session_state.selected_city_view = "Bengaluru (12.97° N, 77.59° E)"

# ==============================================================================
# AUTOMATED RE-ROUTING LOGIC
# ==============================================================================
def check_and_reroute_vehicles():
    """Detects active hazards along upcoming Indian vehicle paths and automatically reroutes them."""
    if not st.session_state.auto_reroute_enabled or not st.session_state.active_hazards:
        return

    for v_id, v_state in st.session_state.fleet_data.items():
        if v_state["status"] in ["Delivered"] or v_state["rerouted"]:
            continue
            
        curr_pos = v_state["current_coord"]
        
        for h_name, h_info in st.session_state.active_hazards.items():
            h_center = h_info["center"]
            h_radius = h_info["radius_km"]
            
            dist_to_hazard = calculate_haversine_distance(curr_pos, h_center)
            intersects_upcoming = any(
                calculate_haversine_distance(wp, h_center) <= h_radius 
                for wp in v_state["waypoints"][1:]
            )
            
            if dist_to_hazard <= (h_radius + 0.5) or intersects_upcoming:
                curr_lat, curr_lon = curr_pos
                dest_lat, dest_lon = v_state["waypoints"][-1]
                
                # Offset bypass around hazard center within India bounds
                offset_lon = 0.025 if curr_lon < h_center[1] else -0.025
                offset_lat = 0.020 if curr_lat < h_center[1] else -0.020
                
                bypass_pt1 = [
                    max(INDIA_MIN_LAT, min(INDIA_MAX_LAT, curr_lat + offset_lat)), 
                    max(INDIA_MIN_LON, min(INDIA_MAX_LON, curr_lon + offset_lon))
                ]
                bypass_pt2 = [
                    max(INDIA_MIN_LAT, min(INDIA_MAX_LAT, dest_lat - offset_lat)), 
                    max(INDIA_MIN_LON, min(INDIA_MAX_LON, dest_lon + offset_lon))
                ]
                
                new_wps = [curr_pos, bypass_pt1, bypass_pt2, [dest_lat, dest_lon]]
                new_segments = [
                    calculate_haversine_distance(new_wps[i], new_wps[i+1]) 
                    for i in range(len(new_wps) - 1)
                ]
                new_total_d = sum(new_segments)
                
                v_state["waypoints"] = new_wps
                v_state["segment_distances"] = new_segments
                v_state["total_distance"] = new_total_d
                v_state["progress_pct"] = 0.0
                v_state["rerouted"] = True
                v_state["status"] = "Rerouted (Traffic Avoided)"
                v_state["reroute_reason"] = f"Avoided {h_name}"
                v_state["color"] = "#9333EA"
                
                event_msg = f"⚡ [{v_id.split(' ')[0]}] Automated re-route activated! Bypass generated around '{h_name}'."
                st.session_state.reroute_events.append({
                    "time": st.session_state.sim_time,
                    "vehicle": v_id.split(' ')[0],
                    "hazard": h_name,
                    "msg": event_msg
                })

# ==============================================================================
# SIMULATION ENGINE STEP FUNCTION
# ==============================================================================
def step_simulation():
    """Advances vehicle positions along Indian route segments based on elapsed speed."""
    st.session_state.sim_time += 1
    step_minutes = 1.0 * st.session_state.speed_multiplier
    
    check_and_reroute_vehicles()
    
    for v_id, v_state in st.session_state.fleet_data.items():
        if v_state["progress_pct"] >= 100.0:
            v_state["status"] = "Delivered"
            continue
            
        dist_step = (v_state["speed"] / 60.0) * (step_minutes / 10.0)
        curr_total_dist = (v_state["progress_pct"] / 100.0) * v_state["total_distance"]
        new_total_dist = min(curr_total_dist + dist_step, v_state["total_distance"])
        
        new_progress = (new_total_dist / v_state["total_distance"]) * 100.0 if v_state["total_distance"] > 0 else 100.0
        v_state["progress_pct"] = new_progress
        
        if new_progress >= 100.0:
            v_state["status"] = "Delivered"
            v_state["current_coord"] = v_state["waypoints"][-1]
            continue
            
        accumulated = 0.0
        wps = v_state["waypoints"]
        for i, seg_d in enumerate(v_state["segment_distances"]):
            if accumulated + seg_d >= new_total_dist:
                seg_fraction = (new_total_dist - accumulated) / seg_d if seg_d > 0 else 0
                c1 = wps[i]
                c2 = wps[i+1]
                new_coord = interpolate_coordinate(c1, c2, seg_fraction)
                # Keep strictly inside India bounds
                new_coord[0] = max(INDIA_MIN_LAT, min(INDIA_MAX_LAT, new_coord[0]))
                new_coord[1] = max(INDIA_MIN_LON, min(INDIA_MAX_LON, new_coord[1]))
                
                bearing = calculate_bearing(c1[0], c1[1], c2[0], c2[1])
                
                v_state["current_coord"] = new_coord
                v_state["bearing"] = bearing
                break
            accumulated += seg_d
            
        speed_fluctuation = np.random.normal(0, 1.5)
        v_state["speed"] = max(15.0, min(65.0, v_state["speed"] + speed_fluctuation))
        v_state["history_speed"].append(v_state["speed"])
        v_state["history_time"].append(st.session_state.sim_time)

# ==============================================================================
# HEADER & CONTROL BAR
# ==============================================================================
st.markdown('<div class="main-header">🇮🇳 Locater 2.0 | Real-Time India Fleet Simulator</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Live GPS Tracking Constrained Strictly Within India Borders</div>', unsafe_allow_html=True)

# Top Control Bar
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([1.8, 1.5, 1.5, 2, 2])

with ctrl_col1:
    live_toggle = st.toggle("🟢 Real-Time Live Loop", value=st.session_state.live_loop_active)
    st.session_state.live_loop_active = live_toggle

with ctrl_col2:
    if st.button("▶️ Step Forward", use_container_width=True):
        step_simulation()

with ctrl_col3:
    if st.button("⏮️ Reset Fleet", use_container_width=True):
        st.session_state.sim_time = 0
        st.session_state.active_hazards = {}
        st.session_state.reroute_events = []
        for v_id, v_info in PREDEFINED_INDIAN_ROUTES.items():
            total_dist = sum(calculate_haversine_distance(v_info["waypoints"][i], v_info["waypoints"][i+1]) for i in range(len(v_info["waypoints"])-1))
            st.session_state.fleet_data[v_id]["waypoints"] = list(v_info["waypoints"])
            st.session_state.fleet_data[v_id]["color"] = v_info["color"]
            st.session_state.fleet_data[v_id]["progress_pct"] = 0.0
            st.session_state.fleet_data[v_id]["current_coord"] = v_info["waypoints"][0]
            st.session_state.fleet_data[v_id]["status"] = "In Transit"
            st.session_state.fleet_data[v_id]["rerouted"] = False
            st.session_state.fleet_data[v_id]["reroute_reason"] = ""
            st.session_state.fleet_data[v_id]["speed"] = v_info["base_speed_kmh"]
            st.session_state.fleet_data[v_id]["history_speed"] = [v_info["base_speed_kmh"]]
            st.session_state.fleet_data[v_id]["history_time"] = [0]

with ctrl_col4:
    st.session_state.speed_multiplier = st.select_slider(
        "Simulation Speed",
        options=[1, 2, 5, 10],
        value=st.session_state.speed_multiplier,
        format_func=lambda x: f"{x}x Speed"
    )

with ctrl_col5:
    st.metric(label="Elapsed Sim Clock", value=f"{st.session_state.sim_time * 2} mins", delta=f"Tick #{st.session_state.sim_time}")

# ==============================================================================
# AUTOMATED RE-ROUTING TRAFFIC HAZARD CONTROL BAR
# ==============================================================================
st.divider()
st.subheader("⚡ Automated Re-Routing & India Traffic Hazards")

haz_col1, haz_col2, haz_col3 = st.columns([2.5, 2, 2.5])

with haz_col1:
    selected_preset = st.selectbox("Simulate Traffic Incident in India", list(TRAFFIC_HAZARD_PRESETS_INDIA.keys()))
    if st.button("⚠️ Trigger Road Closure Hazard", use_container_width=True):
        preset_info = TRAFFIC_HAZARD_PRESETS_INDIA[selected_preset]
        st.session_state.active_hazards[selected_preset] = preset_info
        st.toast(f"Incident triggered in India: {selected_preset}", icon="⚠️")
        check_and_reroute_vehicles()

with haz_col2:
    st.session_state.auto_reroute_enabled = st.toggle(
        "Auto-Rerouting System Enabled", 
        value=st.session_state.auto_reroute_enabled
    )
    if st.button("🧹 Clear Traffic Hazards", use_container_width=True):
        st.session_state.active_hazards = {}
        st.toast("Cleared active road hazards", icon="🧹")

with haz_col3:
    st.session_state.selected_city_view = st.selectbox(
        "Focus Regional Map View",
        ["Bengaluru (12.97° N, 77.59° E)", "Mumbai (19.07° N, 72.87° E)", "Delhi NCR (28.61° N, 77.20° E)", "Entire India View"]
    )

st.divider()

# ==============================================================================
# MAIN LAYOUT: MAP + TELEMETRY SIDEBAR
# ==============================================================================
map_col, tele_col = st.columns([2.2, 1.0])

CITY_CENTERS = {
    "Bengaluru (12.97° N, 77.59° E)": ([12.9300, 77.6500], 11),
    "Mumbai (19.07° N, 72.87° E)": ([19.0300, 72.8800], 11),
    "Delhi NCR (28.61° N, 77.20° E)": ([28.5800, 77.1800], 11),
    "Entire India View": ([20.5937, 78.9629], 5)
}

center_coord, zoom_lvl = CITY_CENTERS[st.session_state.selected_city_view]

with map_col:
    st.subheader("🗺️ Live GPS India Fleet Map (Restricted Bounds: 6.5° N to 35.5° N)")
    
    # Initialize Folium Map centered in India with max_bounds enforced strictly inside India
    m = folium.Map(
        location=center_coord, 
        zoom_start=zoom_lvl, 
        min_zoom=4,
        max_zoom=18,
        tiles="CartoDB positron",
        max_bounds=True,
        min_lat=INDIA_MIN_LAT,
        max_lat=INDIA_MAX_LAT,
        min_lon=INDIA_MIN_LON,
        max_lon=INDIA_MAX_LON
    )
    
    # Add Depots across Indian cities
    for depot_name, depot_coord in DEFAULT_INDIAN_DEPOTS.items():
        folium.Marker(
            location=depot_coord,
            popup=f"<b>🇮🇳 {depot_name}</b><br>Central Logistics Hub",
            tooltip=depot_name,
            icon=folium.Icon(color="black", icon="building", prefix="fa")
        ).add_to(m)
    
    # Render Active Traffic Hazard Overlay Circles in India
    for h_name, h_info in st.session_state.active_hazards.items():
        folium.Circle(
            location=h_info["center"],
            radius=h_info["radius_km"] * 1000,
            color="#DC2626",
            fill=True,
            fill_color="#EF4444",
            fill_opacity=0.35,
            popup=f"<b>⚠️ {h_name}</b><br>{h_info['description']}",
            tooltip=f"India Hazard Zone: {h_name}"
        ).add_to(m)
    
    # Render Fleet Routes & Vehicle Moving Markers in India
    for v_id, v_state in st.session_state.fleet_data.items():
        wps = v_state["waypoints"]
        curr_pos = v_state["current_coord"]
        
        # Polyline for route
        folium.PolyLine(
            locations=wps,
            color=v_state["color"],
            weight=4 if v_state["rerouted"] else 3,
            opacity=0.8 if v_state["rerouted"] else 0.4,
            dash_array="5, 10" if not v_state["rerouted"] else "10, 10"
        ).add_to(m)
        
        # Animated AntPath for visual direction
        AntPath(
            locations=wps,
            color=v_state["color"],
            weight=4,
            opacity=0.8,
            pulse_color="#FFFFFF"
        ).add_to(m)
        
        # Stop Waypoint Markers
        for idx, stop in enumerate(wps[1:], start=1):
            folium.CircleMarker(
                location=stop,
                radius=5,
                color=v_state["color"],
                fill=True,
                fill_color="#FFFFFF",
                popup=f"Stop #{idx} - {v_id}",
                tooltip=f"Drop-off Stop #{idx}"
            ).add_to(m)
            
        # Vehicle Current Moving Marker
        status_badge = "⚡ Rerouted" if v_state["rerouted"] else v_state["status"]
        popup_html = f"""
        <div style='font-family: sans-serif; width: 190px;'>
            <h4 style='margin:0; color:{v_state["color"]};'>{v_id.split(' ')[0]}</h4>
            <b>Region:</b> {v_state['region']}<br>
            <b>Driver:</b> {v_state['driver']}<br>
            <b>Speed:</b> {v_state['speed']:.1f} km/h<br>
            <b>Progress:</b> {v_state['progress_pct']:.1f}%<br>
            <b>Status:</b> {status_badge}<br>
            {"<span style='color:#9333EA; font-weight:bold;'>⚡ " + v_state['reroute_reason'] + "</span>" if v_state['rerouted'] else ""}
        </div>
        """
        
        folium.Marker(
            location=curr_pos,
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{v_id} ({v_state['region']})",
            icon=folium.Icon(
                color="purple" if v_state["rerouted"] else ("red" if v_state["status"]=="Delivered" else "blue"), 
                icon="truck" if not v_state["rerouted"] else "compass", 
                prefix="fa"
            )
        ).add_to(m)
        
    st_folium(m, width="100%", height=530, returned_objects=[])

with tele_col:
    st.subheader("📊 Fleet Telemetry (Locater 2.0)")
    
    for v_id, v_state in st.session_state.fleet_data.items():
        with st.expander(f"🚚 {v_id.split(' ')[0]} ({v_state['region']})", expanded=True):
            if v_state["rerouted"]:
                st.markdown(f"⚡ **Auto-Rerouted:** `{v_state['reroute_reason']}`")
            st.markdown(f"**Driver:** `{v_state['driver']}` ({v_state['type']})")
            
            st.progress(int(v_state["progress_pct"]) / 100.0)
            
            m1, m2 = st.columns(2)
            m1.metric("Speed", f"{v_state['speed']:.1f} km/h")
            m2.metric("Progress", f"{v_state['progress_pct']:.1f}%")
            
            remaining_km = v_state["total_distance"] * (1 - v_state["progress_pct"]/100.0)
            eta_mins = (remaining_km / v_state["speed"] * 60) if v_state["speed"] > 0 else 0
            
            st.caption(f"📦 Cargo Load: **{v_state['cargo']}/{v_state['capacity']} items** ({v_state['cargo']/v_state['capacity']*100:.0f}%)")
            st.caption(f"⏱️ Est. Remaining Time: **{eta_mins:.1f} mins** ({remaining_km:.2f} km left)")

# ==============================================================================
# DISPATCHER, RE-ROUTE LOGS, & ANALYTICS SECTION
# ==============================================================================
st.divider()

tab_analytics, tab_logs, tab_dispatch, tab_about = st.tabs([
    "📈 Speed & Capacity Analytics", 
    "⚡ Automated Re-Routing Logs", 
    "➕ Dispatch Vehicle in India", 
    "ℹ️ Architecture"
])

with tab_analytics:
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Speed Telemetry Over Simulation Time")
        chart_data = []
        for v_id, v_state in st.session_state.fleet_data.items():
            for t, s in zip(v_state["history_time"], v_state["history_speed"]):
                chart_data.append({"Vehicle": v_id.split(' ')[0], "Time Step": t, "Speed (km/h)": s})
        
        if chart_data:
            df_chart = pd.DataFrame(chart_data)
            fig_speed = px.line(
                df_chart, 
                x="Time Step", 
                y="Speed (km/h)", 
                color="Vehicle",
                markers=True,
                line_shape="spline",
                template="plotly_white"
            )
            fig_speed.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig_speed, use_container_width=True)

    with c2:
        st.subheader("Cargo Capacity Utilization Across Fleet")
        fleet_summary = []
        for v_id, v_state in st.session_state.fleet_data.items():
            fleet_summary.append({
                "Vehicle": v_id.split(' ')[0],
                "Cargo Loaded": v_state["cargo"],
                "Capacity": v_state["capacity"],
                "Status": "Rerouted" if v_state["rerouted"] else v_state["status"]
            })
        df_summary = pd.DataFrame(fleet_summary)
        fig_cap = px.bar(
            df_summary, 
            x="Vehicle", 
            y=["Cargo Loaded", "Capacity"], 
            barmode="group",
            template="plotly_white",
            color_discrete_sequence=["#2563EB", "#CBD5E1"]
        )
        fig_cap.update_layout(height=320, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig_cap, use_container_width=True)

with tab_logs:
    st.subheader("⚡ Automated Re-Routing Event Ledger (Locater 2.0)")
    if st.session_state.reroute_events:
        df_logs = pd.DataFrame(st.session_state.reroute_events)
        st.dataframe(df_logs, use_container_width=True)
    else:
        st.info("No re-routing events recorded yet. Trigger a traffic hazard above to test automated detour calculation.")

with tab_dispatch:
    st.subheader("Dispatch a New Vehicle in India")
    with st.form("dispatch_form_india"):
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            new_driver = st.text_input("Driver Name", value="Vikram Singh")
            new_vtype = st.selectbox("Vehicle Type", ["Delivery Van", "Electric Auto Courier", "Heavy Cargo Truck"])
            new_region = st.text_input("Region / City", value="Chennai, TN")
        with col_d2:
            new_capacity = st.number_input("Cargo Capacity (Items)", min_value=10, max_value=300, value=100)
            new_cargo = st.number_input("Loaded Cargo Count", min_value=1, max_value=300, value=75)
        with col_d3:
            new_speed = st.slider("Cruising Speed (km/h)", 20, 70, 40)
            new_color = st.color_picker("Map Marker Color", "#10B981")
            
        st.markdown("**Select Route Waypoints (Constrained within India: 6.5° N - 35.5° N, 68.0° E - 97.5° E):**")
        w1_lat = st.number_input("Start Lat (India)", value=13.0827, min_value=INDIA_MIN_LAT, max_value=INDIA_MAX_LAT, format="%.4f")
        w1_lon = st.number_input("Start Lon (India)", value=80.2707, min_value=INDIA_MIN_LON, max_value=INDIA_MAX_LON, format="%.4f")
        w2_lat = st.number_input("Destination Lat (India)", value=12.9716, min_value=INDIA_MIN_LAT, max_value=INDIA_MAX_LAT, format="%.4f")
        w2_lon = st.number_input("Destination Lon (India)", value=77.5946, min_value=INDIA_MIN_LON, max_value=INDIA_MAX_LON, format="%.4f")
        
        submitted = st.form_submit_button("🚀 Launch Vehicle in India")
        if submitted:
            new_id = f"Vehicle-{101 + len(st.session_state.fleet_data)} ({new_vtype})"
            wps = [[w1_lat, w1_lon], [w1_lat + (w2_lat-w1_lat)*0.5, w1_lon + (w2_lon-w1_lon)*0.5], [w2_lat, w2_lon]]
            tot_d = sum(calculate_haversine_distance(wps[i], wps[i+1]) for i in range(len(wps)-1))
            seg_d = [calculate_haversine_distance(wps[i], wps[i+1]) for i in range(len(wps)-1)]
            
            st.session_state.fleet_data[new_id] = {
                "driver": new_driver,
                "type": new_vtype,
                "color": new_color,
                "region": new_region,
                "capacity": new_capacity,
                "cargo": new_cargo,
                "speed": float(new_speed),
                "waypoints": wps,
                "original_waypoints": list(wps),
                "segment_distances": seg_d,
                "total_distance": tot_d,
                "progress_pct": 0.0,
                "current_coord": wps[0],
                "bearing": 0.0,
                "status": "In Transit",
                "rerouted": False,
                "reroute_reason": "",
                "history_speed": [float(new_speed)],
                "history_time": [st.session_state.sim_time]
            }
            st.success(f"Vehicle `{new_id}` successfully dispatched in India!")
            st.rerun()

with tab_about:
    st.markdown("""
    ### 🔬 Technical Implementation & Grounding
    This application implements real-time vehicle movement simulation and automated re-routing techniques grounded in your notebook research:
    * **India Boundary Lock**: Strict latitude/longitude constraints (6.5° N - 35.5° N, 68.0° E - 97.5° E) ensuring map bounds stay in India.
    * **Live Loop Animation**: Automatic background timer loop advancing vehicle coordinates in real time.
    * **Automated Geofenced Detour Calculation**: Detects road closure hazard zones in Indian metro cities and dynamically calculates alternate waypoint vectors.
    """)

# ==============================================================================
# LIVE REAL-TIME LOOP AUTO-RERUN
# ==============================================================================
if st.session_state.live_loop_active:
    time.sleep(1.0)
    step_simulation()
    st.rerun()
