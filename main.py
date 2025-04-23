import streamlit as st

# Set page configuration
st.set_page_config(
    page_title="CFO Agent",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Main header
st.title("CFO Agent - Ledger")
st.subheader("Your AI Bookkeeping and Accounting Assistant")

# Basic dashboard UI
st.write("Welcome to the Ledger CFO Agent. This application is running in Cloud Run.")

# Health status
st.success("✅ Service is healthy and running")

# Basic content
st.markdown("""
## Features

- **Automated Invoice Processing**: Generate invoices from email requests
- **Financial Analysis**: Get insights into your business finances
- **Tax Planning**: Stay ahead of your tax obligations
- **Cash Flow Management**: Monitor and forecast your cash flow

## Getting Started

Use the sidebar to navigate between different modules of the application.
""")

# Placeholder sidebar for navigation
st.sidebar.title("Navigation")
st.sidebar.markdown("## Modules")
options = st.sidebar.selectbox(
    "Select a module",
    ["Dashboard", "Invoices", "Reports", "Settings"]
)

# Footer
st.markdown("---")
st.markdown("### CFO Agent © 2023 | Running on Google Cloud Run") 