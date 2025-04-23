import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from quickbooks_api import QuickBooksAPI
from config import config
from logger import cfo_logger

class AccountingEngine:
    """Core accounting engine for the CFO Agent.
    
    Processes financial data, computes metrics, and generates reports.
    """
    
    def __init__(self, api_instance=None):
        """Initialize the accounting engine."""
        try:
            self.qb_api = api_instance if api_instance else QuickBooksAPI()
            self.accounts = None
            self.transactions = None
            self.invoices = None
            self.bills = None
            cfo_logger.info("Accounting engine initialized successfully")
        except Exception as e:
            cfo_logger.error(f"Error initializing accounting engine: {str(e)}")
            raise
        
    def refresh_data(self, days_lookback=90):
        """Refresh all financial data from the accounting system."""
        try:
            # Validate input
            if not isinstance(days_lookback, int) or days_lookback <= 0:
                cfo_logger.warning(f"Invalid days_lookback value: {days_lookback}. Must be a positive integer. Using default of 90.")
                days_lookback = 90
                
            cfo_logger.info(f"Refreshing financial data from QuickBooks (lookback: {days_lookback} days)")
            start_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            
            # Use try-except for each API call to ensure partial data if some calls fail
            try:
                self.accounts = self.qb_api.get_accounts()
                cfo_logger.info("Successfully loaded accounts data")
            except Exception as e:
                self.accounts = None
                cfo_logger.error(f"Error loading accounts data: {str(e)}")
                
            try:
                self.transactions = self.qb_api.get_transactions(start_date, end_date)
                cfo_logger.info("Successfully loaded transactions data")
            except Exception as e:
                self.transactions = None
                cfo_logger.error(f"Error loading transactions data: {str(e)}")
                
            try:
                self.invoices = self.qb_api.get_invoices(start_date, end_date)
                cfo_logger.info("Successfully loaded invoices data")
            except Exception as e:
                self.invoices = None
                cfo_logger.error(f"Error loading invoices data: {str(e)}")
                
            try:
                self.bills = self.qb_api.get_bills(start_date, end_date)
                cfo_logger.info("Successfully loaded bills data")
            except Exception as e:
                self.bills = None
                cfo_logger.error(f"Error loading bills data: {str(e)}")
            
            # Return counts of loaded items
            account_count = len(self.accounts.get("QueryResponse", {}).get("Account", [])) if self.accounts else 0
            txn_count = len(self.transactions.get("QueryResponse", {}).get("Transaction", [])) if self.transactions else 0
            invoice_count = len(self.invoices.get("QueryResponse", {}).get("Invoice", [])) if self.invoices else 0
            bill_count = len(self.bills.get("QueryResponse", {}).get("Bill", [])) if self.bills else 0
            
            if account_count == 0 and txn_count == 0 and invoice_count == 0 and bill_count == 0:
                cfo_logger.warning("No financial data was loaded. Verify API credentials and connectivity.")
            else:
                cfo_logger.info("Successfully refreshed financial data")
                
            return {
                "accounts": account_count,
                "transactions": txn_count,
                "invoices": invoice_count,
                "bills": bill_count
            }
            
        except Exception as e:
            cfo_logger.error(f"Error refreshing financial data: {str(e)}")
            # Return empty result on error rather than raising exception
            return {
                "accounts": 0,
                "transactions": 0,
                "invoices": 0,
                "bills": 0,
                "error": str(e)
            }
            
    def get_profit_and_loss(self, start_date=None, end_date=None, format="dataframe"):
        """Generate a profit and loss report."""
        try:
            if not start_date:
                start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
                
            pl_data = self.qb_api.get_profit_and_loss(start_date, end_date)
            
            if format == "raw":
                return pl_data
            
            # Process into a pandas DataFrame for easier analysis
            rows = []
            
            # Extract header information
            header = pl_data.get("Header", {})
            report_name = header.get("ReportName", "Profit and Loss")
            time_period = f"{header.get('StartPeriod', start_date)} to {header.get('EndPeriod', end_date)}"
            
            # Process rows
            if "Rows" in pl_data and "Row" in pl_data["Rows"]:
                for section in pl_data["Rows"]["Row"]:
                    self._process_report_section(section, rows, 0)
            else:
                cfo_logger.warning("No rows found in profit and loss data")
                
            # Create DataFrame
            if rows:
                df = pd.DataFrame(rows)
                
                # Add metadata
                metadata = {
                    "report_name": report_name,
                    "time_period": time_period,
                    "start_date": start_date,
                    "end_date": end_date,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                return {"data": df, "metadata": metadata} if format == "dataframe" else df.to_dict(orient="records")
            else:
                cfo_logger.warning("No data processed for profit and loss report")
                empty_df = pd.DataFrame(columns=["level", "type", "name", "amount"])
                
                # Add metadata even for empty report
                metadata = {
                    "report_name": report_name,
                    "time_period": time_period,
                    "start_date": start_date,
                    "end_date": end_date,
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "No data available for this period"
                }
                
                return {"data": empty_df, "metadata": metadata} if format == "dataframe" else []
            
        except Exception as e:
            cfo_logger.error(f"Error generating profit and loss report: {str(e)}")
            # Return minimal valid data structure to avoid breaking UI
            empty_df = pd.DataFrame(columns=["level", "type", "name", "amount"])
            metadata = {
                "report_name": "Profit and Loss (Error)",
                "time_period": f"{start_date} to {end_date}",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "error": str(e)
            }
            return {"data": empty_df, "metadata": metadata} if format == "dataframe" else []
            
    def get_balance_sheet(self, as_of_date=None, format="dataframe"):
        """Generate a balance sheet report."""
        try:
            if not as_of_date:
                as_of_date = datetime.now().strftime("%Y-%m-%d")
                
            bs_data = self.qb_api.get_balance_sheet(as_of_date)
            
            if format == "raw":
                return bs_data
            
            # Process into a pandas DataFrame for easier analysis
            rows = []
            
            # Extract header information
            header = bs_data.get("Header", {})
            report_name = header.get("ReportName")
            time_period = header.get("Time")
            
            # Process rows
            for section in bs_data.get("Rows", {}).get("Row", []):
                self._process_report_section(section, rows, 0)
                
            # Create DataFrame
            df = pd.DataFrame(rows)
            
            # Add metadata
            metadata = {
                "report_name": report_name,
                "time_period": time_period,
                "as_of_date": as_of_date,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return {"data": df, "metadata": metadata} if format == "dataframe" else df.to_dict(orient="records")
            
        except Exception as e:
            cfo_logger.error(f"Error generating balance sheet report: {str(e)}")
            raise
            
    def get_cash_flow(self, start_date=None, end_date=None, format="dataframe"):
        """Generate a cash flow report."""
        try:
            if not start_date:
                start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            if not end_date:
                end_date = datetime.now().strftime("%Y-%m-%d")
                
            cf_data = self.qb_api.get_cash_flow(start_date, end_date)
            
            if format == "raw":
                return cf_data
            
            # Process into a pandas DataFrame for easier analysis
            rows = []
            
            # Extract header information
            header = cf_data.get("Header", {})
            report_name = header.get("ReportName")
            time_period = f"{header.get('StartPeriod')} to {header.get('EndPeriod')}"
            
            # Process rows
            for section in cf_data.get("Rows", {}).get("Row", []):
                self._process_report_section(section, rows, 0)
                
            # Create DataFrame
            df = pd.DataFrame(rows)
            
            # Add metadata
            metadata = {
                "report_name": report_name,
                "time_period": time_period,
                "start_date": start_date,
                "end_date": end_date,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return {"data": df, "metadata": metadata} if format == "dataframe" else df.to_dict(orient="records")
            
        except Exception as e:
            cfo_logger.error(f"Error generating cash flow report: {str(e)}")
            raise
            
    def _process_report_section(self, section, rows, level=0):
        """Process a section of a financial report recursively."""
        # Skip headers
        if section.get("Header", {}).get("ColData"):
            return
            
        # Process this row
        row_type = section.get("type", "")
        
        if row_type in ["Section", "Data"]:
            # Add this row
            row_data = {
                "level": level,
                "type": row_type,
                "name": section.get("Summary", {}).get("ColData", [{}])[0].get("value", ""),
                "amount": section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "")
            }
            rows.append(row_data)
            
            # Process children
            if "Rows" in section and "Row" in section["Rows"]:
                for child in section["Rows"]["Row"]:
                    self._process_report_section(child, rows, level + 1)
                    
    def get_financial_kpis(self):
        """Calculate key financial performance indicators."""
        try:
            # Get recent financial data
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            start_date_90d = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            
            # Balance sheet as of today
            bs = self.get_balance_sheet(format="raw")
            
            # Profit and Loss for last 30 days and 90 days
            pl_30d = self.qb_api.get_profit_and_loss(start_date_30d, end_date)
            pl_90d = self.qb_api.get_profit_and_loss(start_date_90d, end_date)
            
            # Extract key metrics
            kpis = {}
            
            # Extract total assets from balance sheet
            assets_section = self._find_section_by_name(bs.get("Rows", {}).get("Row", []), "Total Assets")
            total_assets = float(assets_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if assets_section else 0
            
            # Extract total liabilities from balance sheet
            liabilities_section = self._find_section_by_name(bs.get("Rows", {}).get("Row", []), "Total Liabilities")
            total_liabilities = float(liabilities_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if liabilities_section else 0
            
            # Extract equity from balance sheet
            equity_section = self._find_section_by_name(bs.get("Rows", {}).get("Row", []), "Total Equity")
            total_equity = float(equity_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if equity_section else 0
            
            # Extract revenue and expenses from P&L
            revenue_30d_section = self._find_section_by_name(pl_30d.get("Rows", {}).get("Row", []), "Total Income")
            revenue_30d = float(revenue_30d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if revenue_30d_section else 0
            
            revenue_90d_section = self._find_section_by_name(pl_90d.get("Rows", {}).get("Row", []), "Total Income")
            revenue_90d = float(revenue_90d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if revenue_90d_section else 0
            
            expenses_30d_section = self._find_section_by_name(pl_30d.get("Rows", {}).get("Row", []), "Total Expenses")
            expenses_30d = float(expenses_30d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if expenses_30d_section else 0
            
            expenses_90d_section = self._find_section_by_name(pl_90d.get("Rows", {}).get("Row", []), "Total Expenses")
            expenses_90d = float(expenses_90d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if expenses_90d_section else 0
            
            net_income_30d_section = self._find_section_by_name(pl_30d.get("Rows", {}).get("Row", []), "Net Income")
            net_income_30d = float(net_income_30d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if net_income_30d_section else 0
            
            net_income_90d_section = self._find_section_by_name(pl_90d.get("Rows", {}).get("Row", []), "Net Income")
            net_income_90d = float(net_income_90d_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", "")) if net_income_90d_section else 0
            
            # Calculate KPIs
            kpis = {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "debt_to_equity_ratio": total_liabilities / total_equity if total_equity else None,
                "current_ratio": self._calculate_current_ratio(bs),
                "revenue_30d": revenue_30d,
                "revenue_90d": revenue_90d,
                "expenses_30d": expenses_30d,
                "expenses_90d": expenses_90d,
                "net_income_30d": net_income_30d,
                "net_income_90d": net_income_90d,
                "profit_margin_30d": (net_income_30d / revenue_30d) * 100 if revenue_30d else None,
                "profit_margin_90d": (net_income_90d / revenue_90d) * 100 if revenue_90d else None,
                "revenue_growth_rate": ((revenue_30d / (revenue_90d - revenue_30d)) * 100) if (revenue_90d - revenue_30d) else None,
                "cash_on_hand": self._extract_cash_on_hand(bs),
                "accounts_receivable": self._extract_accounts_receivable(bs),
                "accounts_payable": self._extract_accounts_payable(bs)
            }
            
            return kpis
            
        except Exception as e:
            cfo_logger.error(f"Error calculating financial KPIs: {str(e)}")
            return {}
            
    def _find_section_by_name(self, rows, section_name):
        """Find a section in a financial report by name."""
        for row in rows:
            summary = row.get("Summary", {})
            col_data = summary.get("ColData", [])
            if col_data and col_data[0].get("value") == section_name:
                return row
                
            # Check children
            if "Rows" in row and "Row" in row["Rows"]:
                found = self._find_section_by_name(row["Rows"]["Row"], section_name)
                if found:
                    return found
                    
        return None
        
    def _calculate_current_ratio(self, balance_sheet):
        """Calculate the current ratio from a balance sheet."""
        current_assets_section = self._find_section_by_name(
            balance_sheet.get("Rows", {}).get("Row", []), 
            "Total Current Assets"
        )
        
        current_liabilities_section = self._find_section_by_name(
            balance_sheet.get("Rows", {}).get("Row", []),
            "Total Current Liabilities"
        )
        
        if current_assets_section and current_liabilities_section:
            current_assets = float(current_assets_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
            current_liabilities = float(current_liabilities_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
            
            return current_assets / current_liabilities if current_liabilities else None
        
        return None
        
    def _extract_cash_on_hand(self, balance_sheet):
        """Extract cash on hand from a balance sheet."""
        cash_section = self._find_section_by_name(
            balance_sheet.get("Rows", {}).get("Row", []),
            "Cash and Cash Equivalents"
        )
        
        if not cash_section:
            cash_section = self._find_section_by_name(
                balance_sheet.get("Rows", {}).get("Row", []),
                "Bank Accounts"
            )
            
        if cash_section:
            return float(cash_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
            
        return 0
        
    def _extract_accounts_receivable(self, balance_sheet):
        """Extract accounts receivable from a balance sheet."""
        ar_section = self._find_section_by_name(
            balance_sheet.get("Rows", {}).get("Row", []),
            "Accounts Receivable"
        )
        
        if ar_section:
            return float(ar_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
            
        return 0
        
    def _extract_accounts_payable(self, balance_sheet):
        """Extract accounts payable from a balance sheet."""
        ap_section = self._find_section_by_name(
            balance_sheet.get("Rows", {}).get("Row", []),
            "Accounts Payable"
        )
        
        if ap_section:
            return float(ap_section.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
            
        return 0
        
    def forecast_cash_flow(self, months_ahead=3):
        """Forecast cash flow for the specified number of months ahead."""
        try:
            # Get recent invoices and bills
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
            
            invoices = self.qb_api.get_invoices(start_date, end_date)
            bills = self.qb_api.get_bills(start_date, end_date)
            
            # Current cash position
            kpis = self.get_financial_kpis()
            current_cash = kpis.get("cash_on_hand", 0)
            
            # Process invoices for expected inflows
            invoice_items = invoices.get("QueryResponse", {}).get("Invoice", [])
            expected_inflows = []
            
            for invoice in invoice_items:
                if invoice.get("Balance", 0) > 0:
                    due_date = invoice.get("DueDate", "")
                    if due_date:
                        due_date = datetime.strptime(due_date, "%Y-%m-%d")
                        if due_date <= datetime.now() + timedelta(days=months_ahead * 30):
                            expected_inflows.append({
                                "date": due_date.strftime("%Y-%m-%d"),
                                "amount": float(invoice.get("Balance", 0)),
                                "description": f"Invoice #{invoice.get('DocNumber', '')} - {invoice.get('CustomerRef', {}).get('name', 'Customer')}"
                            })
            
            # Process bills for expected outflows
            bill_items = bills.get("QueryResponse", {}).get("Bill", [])
            expected_outflows = []
            
            for bill in bill_items:
                if bill.get("Balance", 0) > 0:
                    due_date = bill.get("DueDate", "")
                    if due_date:
                        due_date = datetime.strptime(due_date, "%Y-%m-%d")
                        if due_date <= datetime.now() + timedelta(days=months_ahead * 30):
                            expected_outflows.append({
                                "date": due_date.strftime("%Y-%m-%d"),
                                "amount": float(bill.get("Balance", 0)),
                                "description": f"Bill #{bill.get('DocNumber', '')} - {bill.get('VendorRef', {}).get('name', 'Vendor')}"
                            })
            
            # Analyze historical cash flow patterns
            cf_data = self.get_cash_flow(start_date, end_date, format="raw")
            
            # Extract operating activities
            operating_activities = self._find_section_by_name(
                cf_data.get("Rows", {}).get("Row", []),
                "Net cash provided by operating activities"
            )
            
            avg_monthly_operating_cash = 0
            if operating_activities:
                operating_cash = float(operating_activities.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0").replace(",", ""))
                avg_monthly_operating_cash = operating_cash / 6  # Divide by 6 months
            
            # Generate monthly forecast
            forecast = []
            running_cash = current_cash
            
            for month in range(1, months_ahead + 1):
                # Calculate inflows and outflows for this month
                month_start = datetime.now() + timedelta(days=(month-1) * 30)
                month_end = datetime.now() + timedelta(days=month * 30)
                
                # Calculate inflows for this month
                month_inflows = sum(
                    float(inflow["amount"]) 
                    for inflow in expected_inflows
                    if month_start <= datetime.strptime(inflow["date"], "%Y-%m-%d") < month_end
                )
                # Add positive operating cash
                month_inflows += max(0, avg_monthly_operating_cash)
                
                # Calculate outflows for this month
                month_outflows = sum(
                    float(outflow["amount"]) 
                    for outflow in expected_outflows
                    if month_start <= datetime.strptime(outflow["date"], "%Y-%m-%d") < month_end
                )
                # Add negative operating cash (as positive outflow)
                month_outflows += abs(min(0, avg_monthly_operating_cash))
                
                # Calculate ending cash
                ending_cash = running_cash + month_inflows - month_outflows
                
                # Add forecast entry with the structure expected by UI
                forecast.append({
                    "period": month_start.strftime("%Y-%m"),
                    "ending_cash": ending_cash,
                    "inflows": month_inflows,
                    "outflows": month_outflows
                })
                
                running_cash = ending_cash
            
            return forecast
            
        except Exception as e:
            cfo_logger.error(f"Error in cash flow forecast: {str(e)}")
            # Return minimal but valid forecast data structure on error
            return [{
                "period": datetime.now().strftime("%Y-%m"),
                "ending_cash": 0,
                "inflows": 0,
                "outflows": 0
            }] 