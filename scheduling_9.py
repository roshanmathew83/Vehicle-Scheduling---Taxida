import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import plotly.graph_objects as go

st.set_page_config(layout="wide")

def validate_columns(df, required_cols, file_label):
    for col in required_cols:
        if col not in df.columns:
            st.error(f"{file_label}: Could not find column '{col}'")
            return False
    return True

REQUIRED_TRIP_COLUMNS = ['Booking Id',
 'Booking Date',
 'Region',
 'City Name',
 'Source State',
 'Route',
 'To City',
 'Destination',
 'Source State 2',
 'Total Amount',
 'PrePaid/Advances',
 'PrePaid/PostPaid',
 'Start Date (DD-MMM-YYYY)',
 'End Date (DD-MMM-YYYY)',
 'Pickup Time',
 'Customer Name',
 'Trip Type',
 'Car Type']
REQUIRED_CONFIG_COLUMNS = ["Route Group", "Duration", "Break Time", "Max Trips"]

# File uploaders
uploaded_trip_file = st.file_uploader("Upload trip data Excel file", type=["xlsx"])
uploaded_config_file = st.file_uploader("Upload route config Excel file", type=["xlsx"])

if uploaded_trip_file and uploaded_config_file:
    # Load input files
    trip_df = pd.read_excel(uploaded_trip_file)
    config_df = pd.read_excel(uploaded_config_file)

    valid_trip = validate_columns(trip_df, REQUIRED_TRIP_COLUMNS, "Trip File")
    valid_config = validate_columns(config_df, REQUIRED_CONFIG_COLUMNS, "Route Config File")

    if valid_trip and valid_config:
        st.success("Files are valid! Processing...")

    # Step 1: Clean trip data 
    def clean_trip_data(raw_df):
        # Strip and unify pickup time
        raw_df["Pickup Time"] = raw_df["Pickup Time"].astype(str).str.strip()

        # Ensure Start Date is datetime
        raw_df["Start Date (DD-MMM-YYYY)"] = pd.to_datetime(
            raw_df["Start Date (DD-MMM-YYYY)"], errors="coerce"
        )

        # Combine Start Date and Pickup Time into a single datetime column
        raw_df["pickup_datetime"] = pd.to_datetime(
            raw_df["Start Date (DD-MMM-YYYY)"].dt.strftime('%Y-%m-%d') + " " + raw_df["Pickup Time"],
            format='%Y-%m-%d %H:%M:%S',
            errors='coerce'
        )

        # Standardize car type categories
        car_type_map = {
            "AC Mid-Size Plus(Toyota Etios or Equivalent)": "sedan",
            "AC Economy(Wagon R or Equivalent)": "hatchback",  # mapped below to sedan
            "Toyota Innova Crysta(Toyota Innova Crysta)": "SUV",
            "AC SUV Large(Ertiga or Equivalent)": "SUV",
            "AC Minivan(Toyota Innova)": "SUV"
        }

        raw_df["Car_Category"] = raw_df["Car Type"].map(car_type_map).fillna("unknown")

        # Merge Katpadi into Vellore route name
        raw_df['Route'] = raw_df['Route'].replace('Katpadi-Chennai', 'Vellore-Chennai')
        
        # Group hatchback into sedan (if needed for better availability)
        raw_df["Car_Category"] = raw_df["Car_Category"].replace("hatchback", "sedan")
        #raw_df["Car_Category"] = raw_df["Car_Category"].replace("SUV", "sedan")

        # Trim whitespaces and standardize route formatting (optional)
        raw_df["Route"] = raw_df["Route"].astype(str).str.strip()
        raw_df["Route"] = raw_df["Route"].str.replace(r'\s*-\s*', '-', regex=True)  # remove spaces around dash

        return raw_df

    def clean_trip_data_sedan_only(raw_df):
        # Strip and unify pickup time
        raw_df["Pickup Time"] = raw_df["Pickup Time"].astype(str).str.strip()

        # Ensure Start Date is datetime
        raw_df["Start Date (DD-MMM-YYYY)"] = pd.to_datetime(
            raw_df["Start Date (DD-MMM-YYYY)"], errors="coerce"
        )

        # Combine Start Date and Pickup Time into a single datetime column
        raw_df["pickup_datetime"] = pd.to_datetime(
            raw_df["Start Date (DD-MMM-YYYY)"].dt.strftime('%Y-%m-%d') + " " + raw_df["Pickup Time"],
            format='%Y-%m-%d %H:%M:%S',
            errors='coerce'
        )

        # Standardize car type categories
        car_type_map = {
            "AC Mid-Size Plus(Toyota Etios or Equivalent)": "sedan",
            "AC Economy(Wagon R or Equivalent)": "hatchback",  # mapped below to sedan
            "Toyota Innova Crysta(Toyota Innova Crysta)": "SUV",
            "AC SUV Large(Ertiga or Equivalent)": "SUV",
            "AC Minivan(Toyota Innova)": "SUV"
        }

        raw_df["Car_Category"] = raw_df["Car Type"].map(car_type_map).fillna("unknown")

        # Merge Katpadi into Vellore route name
        raw_df['Route'] = raw_df['Route'].replace('Katpadi-Chennai', 'Vellore-Chennai')
        
        # Group hatchback into sedan (if needed for better availability)
        raw_df["Car_Category"] = raw_df["Car_Category"].replace("hatchback", "sedan")
        raw_df["Car_Category"] = raw_df["Car_Category"].replace("SUV", "sedan")

        # Trim whitespaces and standardize route formatting (optional)
        raw_df["Route"] = raw_df["Route"].astype(str).str.strip()
        raw_df["Route"] = raw_df["Route"].str.replace(r'\s*-\s*', '-', regex=True)  # remove spaces around dash

        return raw_df

    #st.subheader("🚗 Sedan-Only Allocation")
    use_only_sedan = st.checkbox("✅ Use only Sedans (replace SUVs)")

    if use_only_sedan:
        cleaned_df = clean_trip_data_sedan_only(trip_df)
    else:
        cleaned_df = clean_trip_data(trip_df)

    # Step 2: Dynamically extract Route Group
    def extract_route_group(route):
        try:
            cities = [city.strip() for city in route.split("-")]
            if len(cities) != 2:
                return "Invalid Route"
            return f"{' ↔ '.join(sorted(cities))}"
        except:
            return "Invalid Route"

    cleaned_df["Route Group"] = cleaned_df["Route"].apply(extract_route_group)
    cleaned_df_sorted = cleaned_df.sort_values(by=["Car_Category", "pickup_datetime"])

    # Step 3: Build route config map from Excel
    route_config_map = {}

    for _, row in config_df.iterrows():
        route_group = row["Route Group"]
        cities = [city.strip() for city in route_group.split("-")]
        if len(cities) != 2:
            continue
        city1, city2 = cities

        # Add both directional mappings with normalized keys
        for leg in [(city1, city2), (city2, city1)]:
            key = "-".join(sorted([leg[0], leg[1]]))  # No extra spaces
            route_config_map[key] = {
                "duration": row["Duration"],
                "break_time": row["Break Time"],
                "max_trips": row["Max Trips"]
            }


    import streamlit as st

    st.markdown("### 🚦 Route Configuration")

    seen = set()  # To avoid duplicates like A-B and B-A
    display_data = []

    for route, config in route_config_map.items():
        city1, city2 = [city.strip() for city in route.split("-")]
        group_key = " ↔ ".join(sorted([city1, city2]))
        
        if group_key not in seen:
            display_data.append({
                "Route Group": group_key,
                "Duration (hrs)": config['duration'],
                "Break Time (hrs)": config['break_time'],
                "Max Trips / Day": config['max_trips']
            })
            seen.add(group_key)

    # Convert to DataFrame for display
    config_display_df = pd.DataFrame(display_data)

    # Show it in Streamlit
    st.dataframe(config_display_df, use_container_width=True)
  
    st.subheader("Filters")

    # Standardize 'Route Group' and 'Car_Category' in data
    config_df['Route Group'] = config_df['Route Group'].astype(str).str.strip()
    cleaned_df_sorted['Route Group'] = cleaned_df_sorted['Route Group'].astype(str).str.strip()
    cleaned_df_sorted['Car_Category'] = cleaned_df_sorted['Car_Category'].astype(str).str.strip()

    #Route Group dropdown
    route_groups = ['All'] + sorted(cleaned_df_sorted['Route Group'].dropna().unique())
    selected_group = st.selectbox("Select Route Group", route_groups)

    #Vehicle Type dropdown
    vehicle_types = ['All'] + sorted(cleaned_df_sorted['Car_Category'].dropna().unique())
    selected_vehicle_type = st.selectbox("Select Vehicle Type", vehicle_types)

    # Apply filters
    filtered_df = cleaned_df_sorted.copy()

    if selected_group != 'All':
        filtered_df = filtered_df[filtered_df['Route Group'].str.strip() == selected_group.strip()]

    if selected_vehicle_type != 'All':
        filtered_df = filtered_df[filtered_df['Car_Category'].str.strip() == selected_vehicle_type.strip()]

    # Step 5: Vehicle allocation using config
    def allocate_vehicles_per_category(trips, route_config_map):
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

            config = route_config_map.get(normalized_route, {"duration": 5, "break_time": 3, "max_trips": 3})
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
                vehicle_id = i + 1
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
                new_vehicle_id = len(vehicles[car_category])
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


    allocation_df, vehicle_counts, vehicle_schedule = allocate_vehicles_per_category(filtered_df, route_config_map)

    # Display vehicle count
    st.subheader("Vehicle Assignment Summary")
    for category, count in vehicle_counts.items():
        st.write(f"**{category}**: {count} vehicles")

    total_vehicles = sum(vehicle_counts.values())
    st.write(f"### 🚗 Total Vehicles Needed: {total_vehicles}")
    

    # Display
    st.subheader("Cleaned Trip Data")
    st.dataframe(cleaned_df)

    st.subheader("Vehicle Allocation")
    st.dataframe(allocation_df)

    def display_utilization():
        # Count the number of trips per vehicle
        vehicle_trip_count = allocation_df.groupby(['Car_Category', 'vehicle_id']).size().reset_index(name='trip_count')

        # Calculate the average trips per vehicle for each category
        average_trips = vehicle_trip_count.groupby('Car_Category')['trip_count'].mean().reset_index(name='average_trips')

        # Merge and calculate utilization difference
        utilization_df = pd.merge(vehicle_trip_count, average_trips, on='Car_Category')
        utilization_df['utilization_diff'] = utilization_df['trip_count'] - utilization_df['average_trips']

        # Over- and under-utilized
        over_utilized = utilization_df[utilization_df['utilization_diff'] > 0].sort_values(by='utilization_diff', ascending=False)
        under_utilized = utilization_df[utilization_df['utilization_diff'] < 0].sort_values(by='utilization_diff', ascending=True)

        # Display in Streamlit
        st.subheader("Top Over-Utilized Vehicles")
        st.dataframe(over_utilized[['Car_Category', 'vehicle_id', 'trip_count', 'utilization_diff']].head(10))

        st.subheader("Top Under-Utilized Vehicles")
        st.dataframe(under_utilized[['Car_Category', 'vehicle_id', 'trip_count', 'utilization_diff']].head(5))

    #if st.button("Show Vehicle Utilization"):
    st.button("Show Vehicle Utilization")
    display_utilization()
        
            
    def plot_vehicle_utilization():
        # Aggregate trips
        trip_data = {'SUV': {}, 'hatchback': {}, 'sedan': {}}

        for category in vehicle_schedule:
            for entry in vehicle_schedule[category]:
                vid = entry['vehicle_id']
                trip_data.setdefault(category, {})
                trip_data[category][vid] = trip_data[category].get(vid, 0) + 1

        fig = go.Figure()

        color_map = {'SUV': 'blue', 'hatchback': 'green', 'sedan': 'red'}
        for category, vehicle_data in trip_data.items():
            if vehicle_data:
                fig.add_trace(go.Scatter(
                    x=list(vehicle_data.keys()),
                    y=list(vehicle_data.values()),
                    mode='lines+markers',
                    name=category,
                    line=dict(color=color_map[category])
                ))

        fig.update_layout(
            title="Vehicle Utilization",
            xaxis_title="Vehicle ID",
            yaxis_title="Trip Count",
            template="plotly_dark",
            legend_title="Vehicle Type"
        )

        st.plotly_chart(fig)

    plot_vehicle_utilization()

    def display_vehicle_schedule():
        st.subheader("View Schedule of a Vehicle")

        selected_category = st.selectbox("Select Car Category", list(vehicle_schedule.keys()))
        vehicle_ids = sorted(set(entry["vehicle_id"] for entry in vehicle_schedule[selected_category]))
        selected_vehicle_id = st.selectbox("Select Vehicle ID", vehicle_ids)

        schedule = [
            entry for entry in vehicle_schedule[selected_category]
            if entry["vehicle_id"] == selected_vehicle_id
        ]

        if schedule:
            st.write(f"🧾 Total Trips for {selected_category} {selected_vehicle_id} - {len(schedule)}")

            schedule_df = pd.DataFrame(schedule).sort_values(by="pickup_time")
            booking_ids = schedule_df["trip"].tolist()

            route_info = allocation_df[allocation_df["Booking Id"].isin(booking_ids)][["Booking Id", "Route"]]
            schedule_df = pd.merge(schedule_df, route_info, left_on="trip", right_on="Booking Id", how="left")
            schedule_df = schedule_df.drop(columns=["Booking Id"]).rename(columns={"trip": "Booking Id"})

            st.dataframe(schedule_df)
        else:
            st.info("No trips found for this vehicle.")

    display_vehicle_schedule()

else:
    st.info("Please upload both the trip data and route config Excel files.")