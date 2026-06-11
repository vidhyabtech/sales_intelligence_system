import datetime
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Sales Management System",
    page_icon="📊",
    layout="wide"
)

# --- 2. SESSION STATE FOR AUTHENTICATION & NAVIGATION ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "branch_id" not in st.session_state:
    st.session_state.branch_id = None

# --- 3. DATABASE UTILITIES ---
def get_db_connection():
    return psycopg2.connect(
        host="127.0.0.1",
        database="sms_db",
        user="postgres",
        password="password",
        port="5432",
    )

def verify_credentials(username, password):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        query = "SELECT user_id, username, password, role, branch_id FROM users_table WHERE username = %s AND password = %s;"
        cursor.execute(query, (username, password))
        return cursor.fetchone()
    except Exception as error:
        st.error(f"❌ Database error: {error}")
        return None
    finally:
        if connection: connection.close()

def fetch_branches():
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT branch_id, branch_name FROM branches_table ORDER BY branch_name;")
        return cursor.fetchall()
    except Exception as error:
        st.error(f"❌ Error fetching branches: {error}")
        return []
    finally:
        if connection: connection.close()

def fetch_sales_dashboard_data(role, branch_id):
    connection = None
    try:
        connection = get_db_connection()
        query = """
            SELECT 
                s.sale_id AS "Sale ID",
                b.branch_name AS "Branch Name",
                s.branch_id,
                s.name AS "Student Name",
                s.mobile_number AS "Mobile Number",
                s.product_name AS "Product Name",
                s.date AS "Joining Date",
                s.gross_sales AS "Gross Sales",
                s.received_amount AS "Received Amount",
                s.pending_amount AS "Pending Amount",
                s.status AS "Status"
            FROM sales_table s
            JOIN branches_table b ON s.branch_id = b.branch_id
        """
        if role == "Admin" and branch_id is not None:
            query += " WHERE s.branch_id = %s "
        
        query += " ORDER BY s.sale_id DESC;"
        
        if role == "Admin" and branch_id is not None:
            df = pd.read_sql_query(query, connection, params=(int(branch_id),))
        else:
            df = pd.read_sql_query(query, connection)
            
        return df
    except Exception as error:
        st.error(f"❌ Error fetching records: {error}")
        return None
    finally:
        if connection: connection.close()

def fetch_distinct_courses():
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        cursor.execute("SELECT DISTINCT product_name FROM sales_table WHERE product_name IS NOT NULL AND product_name != '';")
        courses = [row[0] for row in cursor.fetchall()]
        
        # If database works but table is just empty, return empty list
        return sorted(courses)
        
    except Exception:
        # If the database completely crashes/disconnects, 
        # return empty list so the app doesn't throw a red error screen
        return []
        
    finally:
        if connection: 
            connection.close()

def fetch_payment_methods_summary(role, branch_id):
    connection = None
    try:
        connection = get_db_connection()
        # FIX: Updated ps.amount to ps.amount_paid to match DDL schema
        query = """
            SELECT ps.payment_method AS "Method", SUM(ps.amount_paid) AS "Total Amount"
            FROM payment_split_table ps
            JOIN sales_table s ON ps.sale_id = s.sale_id
            """
        if role == "Admin" and branch_id is not None:
            query += " WHERE s.branch_id = %s GROUP BY ps.payment_method;"
            df = pd.read_sql_query(query, connection, params=(int(branch_id),))
        else:
            query += " GROUP BY ps.payment_method;"
            df = pd.read_sql_query(query, connection)
        return df
    except Exception as error:
        return pd.DataFrame()
    finally:
        if connection: connection.close()

def insert_sales_entry(branch_id, name, mobile_number, product_name, joining_date, gross_sales, status):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # Safely determine the next available ID to prevent key duplication conflicts
        cursor.execute("SELECT COALESCE(MAX(sale_id), 0) + 1 FROM sales_table;")
        next_sale_id = cursor.fetchone()[0]
        
        query = """
            INSERT INTO sales_table (sale_id, branch_id, name, mobile_number, product_name, date, gross_sales, received_amount, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s);
        """
        cursor.execute(query, (
            next_sale_id, branch_id, name, mobile_number, product_name, 
            joining_date, gross_sales, status
        ))
        connection.commit()
        return True
    except Exception as error:
        st.error(f"❌ Failed to insert sale: {error}")
        return False
    finally:
        if connection: connection.close()

def insert_payment_split(sale_id, payment_method, amount, payment_date):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        
        # FIX: Adjusted column name to amount_paid to match your DDL table structure
        query = "INSERT INTO payment_split_table (sale_id, payment_method, amount_paid, payment_date) VALUES (%s, %s, %s, %s);"
        cursor.execute(query, (sale_id, payment_method, amount, payment_date))
        
        # FIX: Python-side manual UPDATE removed. Your PostgreSQL trigger 'trg_after_payment_insert' 
        # handles updates automatically, avoiding any duplicate calculations.
        
        connection.commit()
        return True
    except Exception as error:
        st.error(f"❌ Failed to post payment split: {error}")
        return False
    finally:
        if connection: connection.close()


# --- 4. LOGIN PAGE ---
def show_login_page():
    st.title("Sales Management System")
    with st.container(border=True):
        st.markdown("### 🔒 Security Sign In")
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        if st.button("Access Dashboard", use_container_width=True):
            user_record = verify_credentials(username_input, password_input)
            if user_record:
                st.session_state.logged_in = True
                st.session_state.username = user_record["username"]
                st.session_state.user_role = user_record["role"]
                st.session_state.branch_id = user_record["branch_id"]
                st.rerun()
            else:
                st.error("Invalid credentials.")


# --- 5. MAIN APP WORKSPACE ---
def show_main_app():
    # --- SIDEBAR & NAVIGATION ---
    with st.sidebar:
        st.title("Navigation")
        app_mode = st.radio("Go to", ["📊 Dashboard & Reports", "➕ Data Entry Workspace", "💻 Advanced SQL Engine"])
        st.markdown("---")
        st.write(f"👤 User: **{st.session_state.username}**")
        st.write(f"🔑 Role: **{st.session_state.user_role}**")
        if st.button("Log Out", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.user_role = ""
            st.session_state.branch_id = None
            st.rerun()

    # --- MODE 1: DASHBOARD & REPORTS ---
    if app_mode == "📊 Dashboard & Reports":
        st.title("📈 Student Enrollment Dashboard")
        
        raw_df = fetch_sales_dashboard_data(st.session_state.user_role, st.session_state.branch_id)

        if raw_df is not None and not raw_df.empty:
            raw_df["Joining Date"] = pd.to_datetime(raw_df["Joining Date"]).dt.date
            db_min_date = raw_df["Joining Date"].min()
            db_max_date = raw_df["Joining Date"].max()

            # --- 1. FILTER CONTROLS ---
            st.write("### 🔍 Filter Controls")
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            
            with f_col1:
                branch_options = ["All"] + list(raw_df["Branch Name"].unique()) if st.session_state.user_role == "Super Admin" else list(raw_df["Branch Name"].unique())
                selected_branch = st.selectbox("Branch Name", branch_options)
            with f_col2:
                product_options = ["All"] + list(raw_df["Product Name"].unique())
                selected_product = st.selectbox("Product Name", product_options)
            with f_col3:
                start_date = st.date_input("Start Date", value=db_min_date, min_value=db_min_date, max_value=db_max_date)
            with f_col4:
                end_date = st.date_input("End Date", value=db_max_date, min_value=db_min_date, max_value=db_max_date)

            # --- RUNNING CONTROLS FILTER ---
            filtered_df = raw_df.copy()
            if st.session_state.user_role == "Super Admin" and selected_branch != "All":
                filtered_df = filtered_df[filtered_df["Branch Name"] == selected_branch]
            elif st.session_state.user_role == "Admin":
                filtered_df = filtered_df[filtered_df["Branch Name"] == selected_branch]

            if selected_product != "All":
                filtered_df = filtered_df[filtered_df["Product Name"] == selected_product]
                
            if start_date <= end_date:
                filtered_df = filtered_df[(filtered_df["Joining Date"] >= start_date) & (filtered_df["Joining Date"] <= end_date)]
            else:
                st.error("Error: 'Start Date' cannot be set after your chosen 'End Date'.")

            # --- 2. FINANCIAL SUMMARY ---
            st.markdown("---")
            st.write("### 💵 Financial Summary")
            total_gross = filtered_df["Gross Sales"].sum()
            total_received = filtered_df["Received Amount"].sum()
            total_pending = filtered_df["Pending Amount"].sum()
            pending_pct = (total_pending / total_gross * 100) if total_gross > 0 else 0

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            kpi1.metric("Overall Revenue (Gross)", f"₹{total_gross:,.2f}")
            kpi2.metric("Total Received Amount", f"₹{total_received:,.2f}")
            kpi3.metric("Total Pending Amount", f"₹{total_pending:,.2f}")
            kpi4.metric("Pending Collection Pct", f"{pending_pct:.1f}%")

            # --- SALES DATA VIEW ---
            st.markdown("---")
            st.write("### 📋 Branch Course Records Summary")
            display_columns = [
                "Sale ID", "Branch Name", "Student Name", "Mobile Number", 
                "Product Name", "Joining Date", "Gross Sales", "Received Amount", 
                "Pending Amount", "Status"
            ]

            if not filtered_df.empty:
                formatted_df = filtered_df.copy()
                formatted_df["Gross Sales"] = formatted_df["Gross Sales"].map(lambda x: f"₹{x:,.2f}")
                formatted_df["Received Amount"] = formatted_df["Received Amount"].map(lambda x: f"₹{x:,.2f}")
                formatted_df["Pending Amount"] = formatted_df["Pending Amount"].map(lambda x: f"₹{x:,.2f}")
                
                st.dataframe(formatted_df[display_columns], use_container_width=True, hide_index=True)
            else:
                st.info("No records match your chosen criteria.")

            # --- INSIGHTS & ANALYTICS REPORTING ---
            st.markdown("---")
            st.write("### 📊 Advanced Insights & Reports")
            
            an_col1, an_col2 = st.columns(2)
            
            with an_col1:
                st.write("**Branch-wise Sales Comparison (Amounts in ₹)**")
                branch_comp = raw_df.groupby("Branch Name")[["Gross Sales", "Received Amount"]].sum()
                st.bar_chart(branch_comp)
                
                st.write("**Sales Status Metric Split**")
                status_df = filtered_df.groupby("Status").size().reset_index(name="Count")
                st.dataframe(status_df, use_container_width=True, hide_index=True)

            with an_col2:
                st.write("**Payment Method Split Summary**")
                pay_method_df = fetch_payment_methods_summary(st.session_state.user_role, st.session_state.branch_id)
                if not pay_method_df.empty:
                    pay_method_df["Total Amount"] = pay_method_df["Total Amount"].map(lambda x: f"₹{x:,.2f}")
                    st.dataframe(pay_method_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No payment method entries tracked yet.")
                    
                st.write("**Sales Timeline (Growth Tracking in ₹)**")
                trend_df = filtered_df.groupby("Joining Date")["Gross Sales"].sum().reset_index()
                st.line_chart(trend_df.set_index("Joining Date"))

        else:
            st.info("No active dashboard data available.")

    # --- MODE 2: DATA ENTRY WORKSPACE ---
    elif app_mode == "➕ Data Entry Workspace":
        st.title("📝 sales data registry")
        
        tab1, tab2 = st.tabs(["Registration Details", "Payment Split Details"])
        
        with tab1:
            
            branches = fetch_branches()
            branch_map = {b["branch_name"]: b["branch_id"] for b in branches}
            
            if st.session_state.user_role == "Super Admin":
                b_choice = st.selectbox("Select Target Branch", list(branch_map.keys()))
                target_branch_id = branch_map[b_choice] if b_choice else None
            else:
                target_branch_id = st.session_state.branch_id
                st.info(f"Adding sale id into your assigned Branch ID: **{target_branch_id}**")
            
            col_left, col_right = st.columns(2)
            with col_left:
                s_name = st.text_input("Student Name")
                m_number = st.text_input("Mobile Number")
            with col_right:
                course_options = fetch_distinct_courses()
                p_name = st.selectbox("Select Course Name", course_options)
                j_date = st.date_input("Joining Date", value=datetime.date.today())
                
            g_sales = st.number_input("Gross Sales Amount (₹)", min_value=0.0, step=50.0)
            sale_status = st.selectbox("Initial Order Status", ["Open", "Close"])
            
            if st.button("Publish", type="primary"):
                if s_name and m_number and p_name and target_branch_id:
                    if insert_sales_entry(target_branch_id, s_name, m_number, p_name, j_date, g_sales, sale_status):
                        st.success("🎉 Sales record updated successfully!")
                        st.rerun()
                else:
                    st.error("Please fill in all mandatory fields.")

        with tab2:
            
            raw_sales = fetch_sales_dashboard_data(st.session_state.user_role, st.session_state.branch_id)
            
            if raw_sales is not None and not raw_sales.empty:
                open_sales = raw_sales[raw_sales["Status"] == "Open"]
                
                sale_options = open_sales.apply(lambda r: f"ID {r['Sale ID']} - {r['Student Name']} ({r['Product Name']}) - ₹{r['Pending Amount']} Pending", axis=1).tolist()
                sale_mapping = dict(zip(sale_options, open_sales["Sale ID"]))
                
                selected_sale_str = st.selectbox("Select Sale ID ", sale_options)
                p_method = st.selectbox("Payment method", ["Cash", "UPI", "Card"])
                p_amount = st.number_input("Amount Balance (₹)", min_value=0.01, step=10.0)
                p_date = st.date_input("Payment Date", value=datetime.date.today())
                
                if st.button("Apply", type="primary"):
                    target_sale_id = sale_mapping[selected_sale_str]
                    if insert_payment_split(target_sale_id, p_method, p_amount, p_date):
                        st.success("💳 Payment updated successfully.")
                        st.rerun()
            else:
                st.info("No open sales items discovered to apply in payment split table.")

    # --- MODE 3: ADVANCED SQL ENGINE ---
    elif app_mode == "💻 Advanced SQL Engine":
        st.title("💻 Live SQL Analytics Engine")
        
        sql_library = {
            "1. Retrieve all records from the sales table": {
                "sql": "SELECT sale_id, branch_id, date, name, mobile_number, product_name, gross_sales, received_amount, pending_amount, status FROM sales_table;",
                "category": "Basic Queries"
            },
            "2. Retrieve all records from the branches table": {
                "sql": "SELECT branch_id, branch_name, branch_admin_name FROM branches_table;",
                "category": "Basic Queries"
            },
             "3. Display all sales with status = 'Open'": {
                "sql": "SELECT * FROM sales_table WHERE status = 'Open';",
                "category": "Basic Queries"
            },
            "4. Retrieve all sales belonging to the Chennai branch": {
                "sql": "SELECT s.* FROM sales_table s JOIN branches_table b ON s.branch_id = b.branch_id WHERE b.branch_name = 'Chennai';",
                "category": "Basic Queries"
            },
            "5. Calculate the total received amount across all sales": {
                "sql": "SELECT SUM(received_amount) AS total_received_amount FROM sales_table;",
                "category": "Aggregation Queries"
            },
            "6. Calculate the total pending amount across all sales": {
                "sql": "SELECT SUM(pending_amount) AS total_pending_amount FROM sales_table;",
                "category": "Aggregation Queries"
            },
            "7. Count the total number of sales per branch": {
                "sql": "SELECT b.branch_name, COUNT(s.sale_id) AS total_sales FROM sales_table s JOIN branches_table b ON s.branch_id = b.branch_id GROUP BY b.branch_name;",
                "category": "Aggregation Queries"
            },
            "8. Find the average gross sales amount": {
                "sql": "SELECT AVG(gross_sales) AS average_gross_sales FROM sales_table;",
                "category": "Aggregation Queries"
            },
            "9. Retrieve sales details along with the branch name": {
                "sql": "SELECT s.sale_id, s.name, s.product_name, b.branch_name FROM sales_table s JOIN branches_table b ON s.branch_id = b.branch_id;",
                "category": "Join-Based Queries"
            },
            "10. Show branch-wise total gross sales": {
                "sql": "SELECT b.branch_name, SUM(s.gross_sales) AS total_gross_sales FROM sales_table s JOIN branches_table b ON s.branch_id = b.branch_id GROUP BY b.branch_name ORDER BY total_gross_sales DESC;",
                "category": "Join-Based Queries"
            },
            "11. Display sales along with payment method used": {
                "sql": "SELECT s.sale_id, s.name, ps.payment_method, ps.amount_paid FROM sales_table s JOIN payment_split_table ps ON s.sale_id = ps.sale_id;",
                "category": "Join-Based Queries"
            },
            "12. Retrieve sales along with branch admin name": {
                "sql": "SELECT s.sale_id, s.name AS student_name, u.username AS branch_admin FROM sales_table s JOIN users_table u ON s.branch_id = u.branch_id WHERE u.role = 'Admin';",
                "category": "Join-Based Queries"
            },
            "13. Find sales where the pending amount is greater than 5000": {
                "sql": "SELECT sale_id, name, product_name, pending_amount FROM sales_table WHERE pending_amount > 5000;",
                "category": "Financial Tracking Queries"
            },
            "14. Retrieve top 3 highest gross sales": {
                "sql": "SELECT sale_id, name, product_name, gross_sales FROM sales_table ORDER BY gross_sales DESC LIMIT 3;",
                "category": "Financial Tracking Queries"
            },
            "15. Retrieve monthly sales summary (group by month & year)": {
                "sql": "SELECT EXTRACT(YEAR FROM date) AS sales_year, EXTRACT(MONTH FROM date) AS sales_month, SUM(gross_sales) AS monthly_gross FROM sales_table GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date) ORDER BY sales_year DESC, sales_month DESC;",
                "category": "Financial Tracking Queries"
            }
        }

        query_keys = list(sql_library.keys())
        selected_key = st.selectbox("Choose from Predefined Queries:", query_keys)
        
        if selected_key:
            target_data = sql_library[selected_key]
            st.markdown(f"**Query Classification Tier:** `{target_data['category']}`")
            st.code(target_data["sql"], language="sql")
            
            if st.button("Execute", type="primary"):
                connection = None
                try:
                    connection = get_db_connection()
                    res_df = pd.read_sql_query(target_data["sql"], connection)
                    
                    st.success("🎉query successfully passed.")
                    st.write("#### 📋 Output from database records")
                    if not res_df.empty:
                        st.dataframe(res_df, use_container_width=True, hide_index=True)
                    else:
                        st.info("Query successfully processed, but returned 0 relational output records.")
                                                           
                except Exception as e:
                    st.error(f"❌ Structural Execution Error: {e}")
                finally:
                    if connection: connection.close()

# --- 6. ROUTER ---
if not st.session_state.logged_in:
    show_login_page()
else:
    show_main_app()