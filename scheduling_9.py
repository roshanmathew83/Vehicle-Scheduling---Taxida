import streamlit as st
import pandas as pd

# Title
st.title("Vehicle Allocation Scheduler")

# Load Data
@st.cache_data
def load_data():
    df = pd.read_excel("4_routes_cleaned.xlsx", parse_dates=["pickup_datetime", "Start Date (DD-MMM-YYYY)", "End Date (DD-MMM-YYYY)"])
    
    def get_bidirectional_route(route):
        if "Bangalore" in route and "Chennai" in route:
            return "Chennai ↔ Bangalore"
        elif "Vellore" in route and "Chennai" in route:
            return "Chennai ↔ Vellore"
        else:
            return "Other"
    
    df["Route Group"] = df["Route"].apply(get_bidirectional_route)
    return df

df = load_data()

# Initialize session state if it's the first run
if "reset" not in st.session_state:
    st.session_state.reset = False

def reset_filters():
    st.session_state.selected_route_group = "All"
    st.session_state.selected_vehicle_type = "All"
    st.session_state.trip_duration = 5.0
    st.session_state.break_time = 3.0
    st.session_state.max_trips_vc = 3
    st.session_state.max_trips_cv = 3
    st.session_state.max_trips_bc = 20
    st.session_state.max_trips_cb = 20

# Sidebar Filters
st.sidebar.header("Filter Options")

# Reset button
if st.sidebar.button("🔄 Reset All Filters"):
    reset_filters()

route_group_options = ["All"] + sorted(df["Route Group"].unique())
vehicle_type_options = ["All"] + sorted(df["Car_Category"].unique())

# Route Group Filter
selected_route_group = st.sidebar.selectbox(
    "Select Route Group", route_group_options,
    index=route_group_options.index(st.session_state.get("selected_route_group", "All")),
    key="selected_route_group"
)

# Vehicle Type Filter
selected_vehicle_type = st.sidebar.selectbox(
    "Select Vehicle Type", vehicle_type_options,
    index=vehicle_type_options.index(st.session_state.get("selected_vehicle_type", "All")),
    key="selected_vehicle_type"
)

# Duration and Break Time Filters
# Only update session state if the value is not already set
trip_duration = st.sidebar.slider(
    "Trip Duration (hrs)", 1.0, 24.0,
    value=st.session_state.get("trip_duration", 5.0),
    step=0.5, key="trip_duration"
)

break_time = st.sidebar.slider(
    "Break Time after Trip (hrs)", 0.0, 24.0,
    value=st.session_state.get("break_time", 3.0),
    step=0.5, key="break_time"
)

# Max Trips Filters (1 to 30)
st.sidebar.markdown("### Set Max Trips per Vehicle per Day")
max_trips_vc = st.sidebar.slider("Vellore → Chennai", 1, 10, st.session_state.get("max_trips_vc", 3), key="max_trips_vc")
max_trips_cv = st.sidebar.slider("Chennai → Vellore", 1, 10, st.session_state.get("max_trips_cv", 3), key="max_trips_cv")
max_trips_bc = st.sidebar.slider("Bangalore → Chennai", 1, 5, st.session_state.get("max_trips_bc", 5), key="max_trips_bc")
max_trips_cb = st.sidebar.slider("Chennai → Bangalore", 1, 5, st.session_state.get("max_trips_cb", 5), key="max_trips_cb")

# Apply filters
filtered_df = df.copy()

if selected_route_group != "All":
    filtered_df = filtered_df[filtered_df["Route Group"] == selected_route_group]

if selected_vehicle_type != "All":
    filtered_df = filtered_df[filtered_df["Car_Category"] == selected_vehicle_type]

# Sort trips
df_sorted = filtered_df.sort_values(by=["Car_Category", "pickup_datetime"])

# Allocation function
def allocate_vehicles_per_category(trips):
    route_config = {
        "Chennai-Vellore": {"duration": 3.5, "break_time": 2, "max_trips": 3},
        "Bangalore-Chennai": {"duration": 7, "break_time": 3, "max_trips": 2},
    }

    vehicles = {}
    vehicle_assignments = []
    vehicle_counts = {'SUV': 0, 'hatchback': 0, 'sedan': 0}
    trip_counts = {}
    vehicle_schedule = {'SUV': [], 'hatchback': [], 'sedan': []}
    next_available_times = []
    start_points = []
    vehicle_locations = {'SUV': [], 'hatchback': [], 'sedan': []}

    for _, trip in trips.iterrows():
        route_id = trip["Route"]
        source, destination = route_id.split("-")
        
        # Normalize route (e.g., both "Chennai-Vellore" and "Vellore-Chennai" → "Chennai-Vellore")
        normalized_route = "-".join(sorted([source.strip(), destination.strip()]))

        config = route_config.get(normalized_route, {"duration": 5, "break_time": 3, "max_trips": 3})
        duration = config["duration"]
        break_time = config["break_time"]
        max_trips = config["max_trips"]

        car_category = trip["Car_Category"]
        pickup_time = trip["pickup_datetime"]
        trip_date = pickup_time.date()

        # Initialize if category not present
        if car_category not in vehicles:
            vehicles[car_category] = []
            trip_counts[car_category] = {}
            vehicle_locations[car_category] = []

        assigned = False

        # Try to reuse an existing vehicle
        for i in range(len(vehicles[car_category])):
            available_time = vehicles[car_category][i]
            vehicle_loc = vehicle_locations[car_category][i]
            vehicle_id = i + 1  # i-th vehicle always has ID i+1
            count_for_date = trip_counts[car_category].get(vehicle_id, {}).get(trip_date, 0)

            if available_time <= pickup_time and count_for_date < max_trips and vehicle_loc == source:
                return_time = pickup_time + pd.Timedelta(hours=duration + break_time)

                vehicles[car_category][i] = return_time
                vehicle_locations[car_category][i] = destination
                trip_counts[car_category].setdefault(vehicle_id, {})
                trip_counts[car_category][vehicle_id][trip_date] = count_for_date + 1

                vehicle_assignments.append(vehicle_id)
                next_available_times.append(return_time)
                start_points.append(source)

                vehicle_schedule[car_category].append({
                    "vehicle_id": vehicle_id,
                    "trip": trip["Booking Id"],
                    "pickup_time": pickup_time,
                    "return_time": return_time,
                })

                assigned = True
                break

        # If no existing vehicle was available, create a new one
        if not assigned:
            return_time = pickup_time + pd.Timedelta(hours=duration + break_time)
            vehicles[car_category].append(return_time)
            vehicle_locations[car_category].append(destination)
            new_vehicle_id = len(vehicles[car_category])  # Always assigned sequentially
            trip_counts[car_category].setdefault(new_vehicle_id, {})
            trip_counts[car_category][new_vehicle_id][trip_date] = 1

            vehicle_assignments.append(new_vehicle_id)
            next_available_times.append(return_time)
            start_points.append(source)

            vehicle_schedule[car_category].append({
                "vehicle_id": new_vehicle_id,
                "trip": trip["Booking Id"],
                "pickup_time": pickup_time,
                "return_time": return_time,
            })

        vehicle_counts[car_category] = len(vehicles[car_category])

    # Add results to the dataframe
    trips = trips.copy()
    trips["vehicle_id"] = vehicle_assignments
    trips["next_available_time"] = next_available_times
    trips["start_point"] = start_points

    return trips, vehicle_counts, vehicle_schedule




# Allocation
if not df_sorted.empty:
    allocated_trips, vehicle_counts, vehicle_schedule = allocate_vehicles_per_category(df_sorted)

    st.subheader("Vehicle Assignment Summary")
    for category, count in vehicle_counts.items():
        st.write(f"**{category}**: {count} vehicles")

    total_vehicles = sum(vehicle_counts.values())
    st.write(f"### 🚗 Total Vehicles Needed: {total_vehicles}")

    # Optional: Show the table
    with st.expander("See Trip-wise Allocation"):
        st.dataframe(allocated_trips)
else:
    st.warning("No trips match your current filter selections.")

if not allocated_trips.empty:
    
    def display_utilization():
        # Count the number of trips per vehicle
        vehicle_trip_count = allocated_trips.groupby(['Car_Category', 'vehicle_id']).size().reset_index(name='trip_count')
        
        # Calculate the average trips per vehicle for each category
        average_trips = vehicle_trip_count.groupby('Car_Category')['trip_count'].mean().reset_index(name='average_trips')

        # Merge and calculate utilization difference
        utilization_df = pd.merge(vehicle_trip_count, average_trips, on='Car_Category')
        utilization_df['utilization_diff'] = utilization_df['trip_count'] - utilization_df['average_trips']
        
        # Find top over-utilized and under-utilized vehicles
        over_utilized = utilization_df[utilization_df['utilization_diff'] > 0].sort_values(by='utilization_diff', ascending=False)
        under_utilized = utilization_df[utilization_df['utilization_diff'] < 0].sort_values(by='utilization_diff', ascending=True)
        
        # Display results in Streamlit
        st.subheader("Top Over-Utilized Vehicles")
        st.dataframe(over_utilized[['Car_Category', 'vehicle_id', 'trip_count', 'utilization_diff']].head(3))

        st.subheader("Top Under-Utilized Vehicles")
        st.dataframe(under_utilized[['Car_Category', 'vehicle_id', 'trip_count', 'utilization_diff']].head(3))

    if st.button("Show Vehicle Utilization"):
        display_utilization()

    def display_vehicle_schedule():
        st.subheader("View Schedule of a Vehicle")

        # Let user choose car category
        selected_category = st.selectbox("Select Car Category", list(vehicle_schedule.keys()))

        # Get list of vehicle IDs in selected category
        vehicle_ids = sorted(set(entry["vehicle_id"] for entry in vehicle_schedule[selected_category]))
        selected_vehicle_id = st.selectbox("Select Vehicle ID", vehicle_ids)

        # Filter schedule for selected vehicle
        schedule = [
            entry for entry in vehicle_schedule[selected_category]
            if entry["vehicle_id"] == selected_vehicle_id
        ]

        # Add Route info from original df
        if schedule:
            # Display total number of trips
            st.write(f"🧾 Total Trips for {selected_category} {selected_vehicle_id} - {len(schedule)}")

            # Convert schedule to DataFrame and sort by pickup_time
            schedule_df = pd.DataFrame(schedule).sort_values(by="pickup_time")
            booking_ids = schedule_df["trip"].tolist()

            # Fetch corresponding route info from original df
            route_info = df_sorted[df_sorted["Booking Id"].isin(booking_ids)][["Booking Id", "Route"]]

            # Merge to include Route
            schedule_df = pd.merge(schedule_df, route_info, left_on="trip", right_on="Booking Id", how="left")
            schedule_df = schedule_df.drop(columns=["Booking Id"]).rename(columns={"trip": "Booking Id"})

            st.dataframe(schedule_df)
        else:
            st.info("No trips found for this vehicle.")



    # Call this in your Streamlit layout
    display_vehicle_schedule()

#if st.button("View Vehicle Schedule"):
 #   display_vehicle_schedule()

import plotly.graph_objects as go

def plot_vehicle_utilization():
    # Create dictionaries to hold the number of trips for each vehicle type
    suv_trips = {}
    hatchback_trips = {}
    sedan_trips = {}

    # Loop through vehicle_schedule and aggregate the trips for each category
    for category in vehicle_schedule.keys():
        for entry in vehicle_schedule[category]:
            vehicle_id = entry["vehicle_id"]
            if category == "SUV":
                suv_trips[vehicle_id] = suv_trips.get(vehicle_id, 0) + 1
            elif category == "hatchback":
                hatchback_trips[vehicle_id] = hatchback_trips.get(vehicle_id, 0) + 1
            elif category == "sedan":
                sedan_trips[vehicle_id] = sedan_trips.get(vehicle_id, 0) + 1

    # Create lists for x-axis (vehicle ids) and y-axis (trip counts)
    suv_vehicle_ids = list(suv_trips.keys())
    suv_trip_counts = list(suv_trips.values())
    
    hatchback_vehicle_ids = list(hatchback_trips.keys())
    hatchback_trip_counts = list(hatchback_trips.values())
    
    sedan_vehicle_ids = list(sedan_trips.keys())
    sedan_trip_counts = list(sedan_trips.values())

    # Create the Plotly graph
    fig = go.Figure()

    # Add a curve for each category
    fig.add_trace(go.Scatter(x=suv_vehicle_ids, y=suv_trip_counts, mode='lines+markers', name='SUV', line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=hatchback_vehicle_ids, y=hatchback_trip_counts, mode='lines+markers', name='Hatchback', line=dict(color='green')))
    fig.add_trace(go.Scatter(x=sedan_vehicle_ids, y=sedan_trip_counts, mode='lines+markers', name='Sedan', line=dict(color='red')))

    # Update layout for clarity
    fig.update_layout(
        title="Vehicle Utilization",
        xaxis_title="Vehicle ID",
        yaxis_title="Trip Count",
        template="plotly_dark",
        legend_title="Vehicle Type"
    )

    # Display the graph
    st.plotly_chart(fig)

# Call the function to display the chart
plot_vehicle_utilization()

