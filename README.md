# 🚌 Bus Schedule Optimizer

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-blue.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT">
  <img src="https://img.shields.io/badge/optimizer-Genetic_Algorithm-orange.svg" alt="GA Optimizer">
</p>

An intelligent bus schedule optimization system that uses Genetic Algorithms to minimize unmet passenger demand, reduce operating costs, and eliminate corridor overloads—all while preserving route integrity and stop sequences.

Perfect for transit agencies, campus shuttle systems, and inter-city bus services looking to optimize next-day operations using historical demand data.

---

## 🎯 What It Does

The optimizer analyzes your existing bus schedule and passenger demand to automatically recommend:

- **🔄 Time Shifts**: Move departures by ±15 minutes (configurable) to relieve overloaded corridors
- **➕ Bus Additions**: Add extra buses only when shifting can't meet peak demand
- **➖ Smart Removals**: Drop underutilized runs when pooled corridor capacity safely covers demand
- **🚫 Route Immutability**: Never changes stop sequences or extends routes—only adjusts timing and frequency

### Key Features

✅ **Corridor-Aware Capacity Pooling**: When multiple routes share a link (e.g., CHD→RJP), all buses contribute joint capacity at each minute  
✅ **Per-Bus Trip IDs**: Every recommendation targets a specific bus run for unambiguous dispatch  
✅ **Safety Margins**: Drops only occur when remaining capacity exceeds demand by a configurable buffer (default: 20 seats)  
✅ **Shift-First Policy**: Prefers moving existing capacity before adding new buses to minimize cost  
✅ **Human-Readable Output**: Generates aligned plan.txt and structured plan.csv for easy review and execution  

---

## 📋 How It Works

Input: schedule.csv (routes, stops, times, demand per OD pair)
↓
[Genetic Algorithm Optimizer]
- Evaluates 400 generations (60 population)
- Fitness = Unmet_Penalty × Unmet + Run_Cost + Add_Cost
- Enforces link-time capacity constraints
- Preserves route paths (shift/add/drop only)
↓
Output: plan.txt (human-readable per-bus actions)
plan.csv (structured data for dispatch systems)

---

## 🚀 Quick Start

### Installation

Clone the repository
git clone https://github.com/yourusername/bus-schedule-optimizer.git
cd bus-schedule-optimizer

No external dependencies needed—uses only Python stdlib!
python optimize.py --schedule schedule.csv

### Requirements

- Python 3.8+
- No external packages required (uses `csv`, `random`, `collections`, `math`)

---

## 📊 Input Format

### schedule.csv

Each row represents **one physical bus run** with a unique `trip_id`:

route_id,trip_id,stops_pipe,travel_min_pipe,dep_time,base_buses,passengers,dep_od_pipe
R1,R1-0815-A,CHD|RJP,35,08:15,1,20,CHD:RJP:20
R2,R2-0830-A,CHD|RJP|PAT,35|50,08:30,1,80,CHD:RJP:45|CHD:PAT:35
R1,R1-1400-A,CHD|RJP,35,14:00,1,7,CHD:RJP:7
R2,R2-1415-A,CHD|RJP|PAT,35|50,14:15,1,85,CHD:RJP:50|CHD:PAT:35

#### Column Definitions

| Column | Description | Example |
|--------|-------------|---------|
| `route_id` | Line name (multiple trips can share) | `R1`, `R2` |
| `trip_id` | Unique bus run identifier | `R1-0815-A` |
| `stops_pipe` | Stop sequence separated by pipe | `CHD\|RJP\|PAT` |
| `travel_min_pipe` | Minutes between consecutive stops | `35\|50` (35 min CHD→RJP, 50 min RJP→PAT) |
| `dep_time` | Departure time from first stop (HH:MM) | `08:30` |
| `base_buses` | Number of buses (use 1 for clarity) | `1` |
| `passengers` | Total riders on this trip | `80` |
| `dep_od_pipe` | Origin:Destination:Count groups | `CHD:RJP:45\|CHD:PAT:35` |

---

## 📤 Output Examples

### plan.txt (Human-Readable)

Optimization Plan (per bus)
Route R1
Trip ID(s) From -> To Action Net Baseline
R1-0815-A 08:15 -> 08:30 Shift 0 1
R1-1400-A 14:00 -> 14:15 Shift 0 1
R1-1715-A 17:15 -> 17:15 Drop -1 1

Route R2
Trip ID(s) From -> To Action Net Baseline
R2-0830-A 08:30 -> 08:30 Keep 0 1
R2-1415-A 14:15 -> 14:15 Keep 0 1
R2-1900-A 19:00 -> 19:00 Keep 2 1
R2-1900-B, R2-1900-C 19:00 -> 19:00 Add 2 1

### plan.csv (Machine-Readable)

route_id,original_time,adjusted_time,baseline_buses,net_bus_change,trip_ids_kept,trip_ids_dropped,trip_ids_added
R1,08:15,08:30,1,0,R1-0815-A,,
R1,14:00,14:15,1,0,R1-1400-A,,
R1,17:15,17:15,1,-1,,R1-1715-A,
R2,08:30,08:30,1,0,R2-0830-A,,
R2,19:00,19:00,1,2,R2-1900-A,,R2-1900-B|R2-1900-C

---

## 🔧 Configuration

Edit constants at the top of `optimize.py`:

BUS_CAPACITY = 45 # seats per bus
SHIFT_CHOICES = [-15, 0, 15] # allowed minute offsets
MAX_ADD_PER_DEP = 2 # max buses added per departure
UNMET_PENALTY = 28.0 # cost per unserved passenger
RUN_COST = 3.0 # cost per bus-departure
ADD_COST = 120.0 # fixed cost per added bus
DROP_SAFETY_MARGIN_SEATS = 20 # slack required before dropping
POP_SIZE = 60 # GA population size
GENERATIONS = 400 # GA iterations

---

## 💡 Use Cases

### 1. Morning Corridor Overload
**Problem**: R2 at 08:30 has 80 passengers on CHD→RJP with only 1 bus (45 seats)  
**Solution**: Shift R1-0815-A from 08:15 → 08:30, pooling capacity to 90 seats  
**Result**: Zero unmet demand, no added buses, same routes

### 2. Evening Peak Requiring Additions
**Problem**: R2 at 19:00 has 160 passengers (80 CHD→RJP + 80 CHD→PAT)  
**Solution**: Add 2 buses on R2 at 19:00 (R2-1900-B, R2-1900-C)  
**Result**: CHD→RJP capacity = 135 seats, CHD→PAT capacity = 135 seats, meets demand

### 3. Midday Consolidation
**Problem**: Two R1 buses at 11:00 carry only 20 total passengers  
**Solution**: Drop one bus (e.g., R1-1100-B) when corridor slack ≥ 20 seats  
**Result**: Reduced operating cost, no unmet demand

---

## 🧪 Testing

The optimizer is robust to:
- Missing trip_id (auto-generates stable IDs)
- Different header naming (route/route_id/line, dep_time/time/departure)
- UTF-8 BOM in CSV files
- Multiple buses at the same minute (distinct trip_ids required)

Run on the included test schedules:

python optimize.py --schedule test_morning_overload.csv
python optimize.py --schedule test_evening_peak.csv
python optimize.py --schedule test_mixed_scenarios.csv
---

## 🎓 Algorithm Details

- **Genetic Algorithm** with elitism, tournament selection, single-point crossover
- **Chromosome**: per-departure shift choice + add count + drop count
- **Fitness**: `UNMET_PENALTY × ⌈unmet⌉ + RUN_COST × buses + ADD_COST × added`
- **Capacity Check**: Link-time basis with pooled buses from all routes traversing the link
- **Drop Feasibility**: Allowed only when `remaining_capacity ≥ demand + MARGIN` on all affected link-times
- **Shift Freezing**: Trips with multi-link OD pairs keep original timing to preserve path integrity

---

## 📈 Performance

- Typical runtime: **< 30 seconds** for 20 routes × 10 departures on a laptop
- Scales to hundreds of trips with same per-generation cost
- Deterministic results via fixed random seed (RANDOM_SEED = 13)

---

## 🗺️ Visualizing Routes on a Map

Use **React Native Maps** with Polyline overlays to draw each route:

### Option A: OSRM Routing API
import MapView, { Polyline } from 'react-native-maps';

// Fetch route geometry
const response = await fetch(
'https://router.project-osrm.org/route/v1/driving/LON1,LAT1;LON2,LAT2?geometries=geojson&overview=full'
);
const { routes } = await response.json();
const coords = routes.geometry.coordinates.map(([lon, lat]) => ({ latitude: lat, longitude: lon }));

// Render
<MapView>
<Polyline coordinates={coords} strokeWidth={4} strokeColor="#1976D2" />
</MapView>

### Option B: GTFS shapes.txt
If you have GTFS data, read `shapes.txt` to get exact route paths:
shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence
R1_shape,30.7333,76.7794,1
R1_shape,30.7412,76.7850,2


Then map each route to its shape and render as Polylines on the map for accurate visual representation.

---

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- **Real-time demand forecasting** integration
- **Multi-day optimization** with rolling horizon
- **Vehicle assignment** to minimize deadhead miles
- **Crew scheduling** constraints
- **Web UI** for non-technical planners

---

## 📜 License

MIT License - feel free to use in commercial transit systems.

---

## 🙏 Acknowledgments

Inspired by GTFS schedule semantics and genetic algorithm approaches to vehicle routing problems. Built for real-world bus tracking apps serving college campuses and inter-city corridors.

---

## 📞 Contact

- **Issues**: [GitHub Issues](https://github.com/yourusername/bus-schedule-optimizer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/bus-schedule-optimizer/discussions)

---

**⭐ Star this repo if it helps your transit operations!**

