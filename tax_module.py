import os
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from logger import cfo_logger

class TaxModule:
    """Tax planning and preparation module for the CFO Agent.
    
    Handles tax estimation, deduction analysis, and filing preparation.
    """
    
    def __init__(self, accounting_engine):
        """Initialize the tax module."""
        try:
            self.accounting_engine = accounting_engine
            self.tax_rates = self._load_tax_rates()
            self.company_name = os.getenv("COMPANY_NAME", "Sample Company")
            self.company_tax_id = os.getenv("COMPANY_TAX_ID", "XX-XXXXXXX")
            cfo_logger.info("Tax module initialized successfully")
        except Exception as e:
            cfo_logger.error(f"Error initializing tax module: {str(e)}")
            # Set defaults in case of error
            self.tax_rates = {
                "federal": {"brackets": [[0, 0.21]]},
                "state": {"flat_rate": 0.05}
            }
            self.company_name = "Sample Company"
            self.company_tax_id = "XX-XXXXXXX"
            
    def _load_tax_rates(self):
        """Load tax rates from configuration."""
        try:
            # In a production environment, this would load from a proper source
            # For this example, use hardcoded rates
            return {
                "federal": {
                    "brackets": [
                        [0, 0.10],
                        [9950, 0.12],
                        [40525, 0.22],
                        [86375, 0.24],
                        [164925, 0.32],
                        [209425, 0.35],
                        [523600, 0.37]
                    ]
                },
                "state": {
                    "flat_rate": 0.05  # Example state with flat rate
                }
            }
        except Exception as e:
            cfo_logger.error(f"Error loading tax rates: {str(e)}")
            # Return default rates in case of error
            return {
                "federal": {"brackets": [[0, 0.21]]},
                "state": {"flat_rate": 0.05}
            }
            
    def calculate_estimated_taxes(self, tax_year=None):
        """Calculate estimated taxes based on current financial data."""
        try:
            if not tax_year:
                tax_year = datetime.now().year
                
            # Get financial data from accounting engine
            start_date = f"{tax_year}-01-01"
            end_date = datetime.now().strftime("%Y-%m-%d") if tax_year == datetime.now().year else f"{tax_year}-12-31"
            
            try:
                pl_data = self.accounting_engine.get_profit_and_loss(start_date, end_date, format="raw")
                if not pl_data or not isinstance(pl_data, dict):
                    raise ValueError(f"Invalid profit and loss data returned - type: {type(pl_data)}")
            except Exception as api_error:
                cfo_logger.error(f"Error retrieving profit and loss data: {str(api_error)}")
                return {
                    "tax_year": tax_year,
                    "net_income_to_date": 0,
                    "days_elapsed": 0,
                    "annualized_income": 0,
                    "federal_tax_estimate": 0,
                    "state_tax_estimate": 0,
                    "total_tax_estimate": 0,
                    "quarterly_payment": 0,
                    "payment_schedule": [],
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "Error retrieving financial data"
                }
            
            # Extract net income
            net_income_section = None
            if "Rows" in pl_data and "Row" in pl_data["Rows"]:
                net_income_section = self.accounting_engine._find_section_by_name(
                    pl_data["Rows"]["Row"],
                    "Net Income"
                )
            
            net_income_to_date = 0
            if net_income_section and "Summary" in net_income_section and "ColData" in net_income_section["Summary"]:
                col_data = net_income_section["Summary"]["ColData"]
                if col_data and len(col_data) > 0:
                    value_str = col_data[-1].get("value", "0")
                    net_income_to_date = float(value_str.replace(",", ""))
            
            # Calculate annualized income
            current_date = datetime.now()
            days_elapsed = (current_date - datetime(tax_year, 1, 1)).days if tax_year == current_date.year else 365
            days_in_year = 366 if (tax_year % 4 == 0 and tax_year % 100 != 0) or tax_year % 400 == 0 else 365
            
            annualization_factor = days_in_year / max(days_elapsed, 1)  # Avoid division by zero
            annualized_income = net_income_to_date * annualization_factor
            
            # Calculate federal tax using brackets
            federal_tax = self._calculate_federal_tax(annualized_income)
            
            # Calculate state tax (using flat rate for example)
            state_tax_rate = self.tax_rates.get("state", {}).get("flat_rate", 0.05)
            state_tax = annualized_income * state_tax_rate
            
            # Total tax
            total_tax = federal_tax + state_tax
            
            # Calculate quarterly payment
            remaining_quarters = 4 - min(3, (current_date.month - 1) // 3) if tax_year == current_date.year else 0
            quarterly_payment = total_tax / 4 if remaining_quarters > 0 else 0
            
            # Generate payment schedule
            payment_schedule = []
            
            for quarter in range(1, 5):
                if tax_year == current_date.year:
                    due_month = [4, 6, 9, 1][quarter - 1]
                    due_day = 15
                    due_year = tax_year if quarter < 4 else tax_year + 1
                    due_date = datetime(due_year, due_month, due_day)
                    
                    status = "Past Due" if due_date < current_date else "Upcoming"
                else:
                    due_month = [4, 6, 9, 1][quarter - 1]
                    due_day = 15
                    due_year = tax_year if quarter < 4 else tax_year + 1
                    due_date = datetime(due_year, due_month, due_day)
                    
                    status = "Completed"
                
                payment_schedule.append({
                    "quarter": quarter,
                    "due_date": due_date.strftime("%Y-%m-%d"),
                    "amount": total_tax / 4,
                    "status": status
                })
            
            result = {
                "tax_year": tax_year,
                "net_income_to_date": net_income_to_date,
                "days_elapsed": days_elapsed,
                "annualized_income": annualized_income,
                "federal_tax_estimate": federal_tax,
                "state_tax_estimate": state_tax,
                "total_tax_estimate": total_tax,
                "quarterly_payment": quarterly_payment,
                "payment_schedule": payment_schedule,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return result
            
        except Exception as e:
            cfo_logger.error(f"Error calculating estimated taxes: {str(e)}")
            return {
                "tax_year": tax_year if 'tax_year' in locals() else datetime.now().year,
                "error": str(e),
                "net_income_to_date": 0,
                "federal_tax_estimate": 0,
                "state_tax_estimate": 0,
                "total_tax_estimate": 0,
                "quarterly_payment": 0,
                "payment_schedule": [],
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
    
    def _calculate_federal_tax(self, income):
        """Calculate federal tax using tax brackets."""
        try:
            brackets = self.tax_rates.get("federal", {}).get("brackets", [[0, 0.21]])
            
            tax = 0
            prev_threshold = 0
            
            for i, bracket in enumerate(brackets):
                threshold, rate = bracket
                
                if i == len(brackets) - 1 or income <= brackets[i+1][0]:
                    # In this bracket or the highest bracket
                    tax += (income - threshold) * rate
                    break
                else:
                    # Calculate tax for this bracket range
                    next_threshold = brackets[i+1][0]
                    tax += (next_threshold - threshold) * rate
                    
            return tax
            
        except Exception as e:
            cfo_logger.error(f"Error calculating federal tax: {str(e)}")
            # Fallback calculation for safety
            return income * 0.21
    
    def generate_tax_deduction_report(self, tax_year=None):
        """Generate a report of potential tax deductions."""
        try:
            if not tax_year:
                tax_year = datetime.now().year
                
            # Get expense data from accounting engine
            start_date = f"{tax_year}-01-01"
            end_date = datetime.now().strftime("%Y-%m-%d") if tax_year == datetime.now().year else f"{tax_year}-12-31"
            
            try:
                pl_data = self.accounting_engine.get_profit_and_loss(start_date, end_date, format="raw")
                if not pl_data or not isinstance(pl_data, dict):
                    raise ValueError(f"Invalid profit and loss data returned - type: {type(pl_data)}")
            except Exception as api_error:
                cfo_logger.error(f"Error retrieving profit and loss data: {str(api_error)}")
                return {
                    "tax_year": tax_year,
                    "total_expenses": 0,
                    "total_deductible_amount": 0,
                    "deduction_summary": [],
                    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": "Error retrieving financial data",
                    "error": str(api_error)
                }
            
            # Extract expenses
            expenses_section = None
            if "Rows" in pl_data and "Row" in pl_data["Rows"]:
                expenses_section = self.accounting_engine._find_section_by_name(
                    pl_data["Rows"]["Row"],
                    "Total Expenses"
                )
            
            # Initialize variables
            total_expenses = 0
            expense_categories = []
            
            if expenses_section and "Rows" in expenses_section and "Row" in expenses_section["Rows"]:
                for expense in expenses_section["Rows"]["Row"]:
                    name = expense.get("Summary", {}).get("ColData", [{}])[0].get("value", "Unknown Expense")
                    amount_str = expense.get("Summary", {}).get("ColData", [{}])[-1].get("value", "0")
                    
                    # Clean amount string
                    amount_str = amount_str.replace(",", "").replace("$", "").strip()
                    
                    # Handle negative values (enclosed in parentheses)
                    if amount_str.startswith("(") and amount_str.endswith(")"):
                        amount = -float(amount_str[1:-1])
                    else:
                        amount = float(amount_str)
                    
                    deduction_category = self._map_expense_to_deduction_category(name)
                    deductible_pct = self._get_deductible_percentage(deduction_category)
                    deductible_amount = amount * deductible_pct
                    notes = self._get_deduction_notes(deduction_category)
                    
                    expense_categories.append({
                        "expense_name": name,
                        "amount": amount,
                        "deduction_category": deduction_category,
                        "deductible_percentage": deductible_pct * 100,
                        "deductible_amount": deductible_amount,
                        "notes": notes
                    })
                    
                    total_expenses += amount
            
            # Sort expenses by deductible amount (descending)
            expense_categories.sort(key=lambda x: x["deductible_amount"], reverse=True)
            
            # Calculate total deductible amount
            total_deductible = sum(cat["deductible_amount"] for cat in expense_categories)
            
            # Generate report
            result = {
                "tax_year": tax_year,
                "total_expenses": total_expenses,
                "total_deductible_amount": total_deductible,
                "deduction_summary": expense_categories,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "notes": "This report identifies potential tax deductions. Consult with a tax professional for specific advice."
            }
            
            return result
            
        except Exception as e:
            cfo_logger.error(f"Error generating tax deduction report: {str(e)}")
            return {
                "tax_year": tax_year if 'tax_year' in locals() else datetime.now().year,
                "total_expenses": 0,
                "total_deductible_amount": 0,
                "deduction_summary": [],
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "notes": f"Error: {str(e)}"
            }
    
    def _map_expense_to_deduction_category(self, expense_name):
        """Map an expense name to a standard tax deduction category."""
        try:
            if not expense_name:
                return "Other expenses"
                
            expense_name_lower = expense_name.lower()
            
            # Map common expense names to tax deduction categories
            category_mapping = {
                "advertising": "Advertising",
                "ad": "Advertising",
                "marketing": "Advertising",
                "promotion": "Advertising",
                
                "auto": "Car and truck expenses",
                "vehicle": "Car and truck expenses",
                "car": "Car and truck expenses",
                "truck": "Car and truck expenses",
                "mileage": "Car and truck expenses",
                
                "commission": "Commissions and fees",
                "fee": "Commissions and fees",
                
                "contractor": "Contract labor",
                "consultant": "Contract labor",
                "freelance": "Contract labor",
                
                "depreciation": "Depreciation",
                "amortization": "Depreciation",
                
                "benefits": "Employee benefits",
                "health": "Employee benefits",
                "welfare": "Employee benefits",
                
                "insurance": "Insurance",
                "policy": "Insurance",
                
                "interest": "Interest paid",
                "loan": "Interest paid",
                "debt": "Interest paid",
                
                "legal": "Legal and professional services",
                "professional": "Legal and professional services",
                "accounting": "Legal and professional services",
                "lawyer": "Legal and professional services",
                "attorney": "Legal and professional services",
                
                "office": "Office expenses",
                "supplies": "Supplies",
                "stationery": "Supplies",
                
                "pension": "Pension and profit-sharing plans",
                "401k": "Pension and profit-sharing plans",
                "retirement": "Pension and profit-sharing plans",
                
                "rent": "Rent or lease payments",
                "lease": "Rent or lease payments",
                
                "repair": "Repairs and maintenance",
                "maintenance": "Repairs and maintenance",
                "fix": "Repairs and maintenance",
                
                "tax": "Taxes and licenses",
                "license": "Taxes and licenses",
                "permit": "Taxes and licenses",
                
                "travel": "Travel",
                "airfare": "Travel",
                "hotel": "Travel",
                "lodging": "Travel",
                
                "meal": "Meals",
                "food": "Meals",
                "entertainment": "Meals",
                "dining": "Meals",
                
                "utilities": "Utilities",
                "electric": "Utilities",
                "water": "Utilities",
                "gas": "Utilities",
                "internet": "Utilities",
                "phone": "Utilities",
                
                "salary": "Wages",
                "wage": "Wages",
                "payroll": "Wages",
                "compensation": "Wages"
            }
            
            # Find the closest matching category
            for key, category in category_mapping.items():
                if key in expense_name_lower:
                    return category
                    
            # Default to "Other expenses" if no match is found
            return "Other expenses"
            
        except Exception as e:
            cfo_logger.error(f"Error mapping expense category for '{expense_name}': {str(e)}")
            return "Other expenses"
    
    def _get_deductible_percentage(self, category):
        """Get the deductible percentage for a given expense category."""
        try:
            # Most business expenses are 100% deductible
            deduction_percentages = {
                "Meals": 0.50,  # Meals are typically 50% deductible since 2018
                "Entertainment": 0.0,  # Entertainment is generally not deductible post-2018
                
                # All other categories default to 100%
                "Advertising": 1.0,
                "Car and truck expenses": 1.0,
                "Commissions and fees": 1.0,
                "Contract labor": 1.0,
                "Depreciation": 1.0,
                "Employee benefits": 1.0,
                "Insurance": 1.0,
                "Interest paid": 1.0,
                "Legal and professional services": 1.0,
                "Office expenses": 1.0,
                "Pension and profit-sharing plans": 1.0,
                "Rent or lease payments": 1.0,
                "Repairs and maintenance": 1.0,
                "Supplies": 1.0,
                "Taxes and licenses": 1.0,
                "Travel": 1.0,
                "Utilities": 1.0,
                "Wages": 1.0,
                "Other expenses": 1.0
            }
            
            # Get the percentage or default to 100%
            return deduction_percentages.get(category, 1.0)
            
        except Exception as e:
            cfo_logger.error(f"Error getting deductible percentage for '{category}': {str(e)}")
            return 1.0  # Default to 100% in case of error
    
    def _get_deduction_notes(self, category):
        """Get notes and requirements for a given deduction category."""
        try:
            deduction_notes = {
                "Meals": "Meals must be directly related to business. Keep detailed records of who attended, business purpose, and receipt. Limited to 50% deductible.",
                "Car and truck expenses": "Maintain a mileage log and documentation of business use percentage. Consider standard mileage rate vs. actual expenses.",
                "Travel": "Must be ordinary and necessary for business. Keep receipts and document business purpose. Travel must be away from tax home overnight.",
                "Home office": "Must be used regularly and exclusively for business. Calculate square footage used for business divided by total square footage.",
                "Depreciation": "Assets with useful life > 1 year. Consider Section 179 for immediate expensing (limit $1,080,000 for 2023).",
                "Interest paid": "Must be for business loans or credit. Personal interest is not deductible. Mortgage interest for business property is fully deductible.",
                "Legal and professional services": "Must be for business purposes. Startup costs may need to be amortized. Fees for tax preparation are deductible.",
                "Wages": "Ensure proper W-2 or 1099 filing for all compensation paid. Reasonable compensation requirements apply for S-corporation owners.",
                "Rent or lease payments": "Document terms and ensure payments are at fair market value if leasing from a related party.",
                "Entertainment": "Entertainment expenses are generally no longer deductible after the Tax Cuts and Jobs Act of 2018."
            }
            
            return deduction_notes.get(category, "Keep detailed records and receipts. Expense must be ordinary and necessary for business.")
            
        except Exception as e:
            cfo_logger.error(f"Error getting deduction notes for '{category}': {str(e)}")
            return "Keep detailed records and receipts. Expense must be ordinary and necessary for business."
    
    def prepare_tax_filing_checklist(self):
        """Generate a tax filing preparation checklist based on company type."""
        try:
            # Determine current tax year
            current_year = datetime.now().year
            tax_filing_year = current_year if datetime.now().month > 3 else current_year - 1
            
            # Basic checklist items for all businesses
            checklist = [
                {
                    "category": "Financial Reports",
                    "items": [
                        {"name": f"Profit & Loss Statement for {tax_filing_year}", "status": "Pending"},
                        {"name": f"Balance Sheet as of Dec 31, {tax_filing_year}", "status": "Pending"},
                        {"name": f"General Ledger for {tax_filing_year}", "status": "Pending"},
                        {"name": f"Fixed Asset Schedule for {tax_filing_year}", "status": "Pending"}
                    ]
                },
                {
                    "category": "Income Documentation",
                    "items": [
                        {"name": "All 1099s received", "status": "Pending"},
                        {"name": "Sales records and receipts", "status": "Pending"},
                        {"name": "Income from investments", "status": "Pending"},
                        {"name": "Record of returns and allowances", "status": "Pending"}
                    ]
                },
                {
                    "category": "Expense Documentation",
                    "items": [
                        {"name": "Business travel records and receipts", "status": "Pending"},
                        {"name": "Meals and entertainment receipts", "status": "Pending"},
                        {"name": "Vehicle mileage logs", "status": "Pending"},
                        {"name": "Home office calculation", "status": "Pending"},
                        {"name": "Office supplies and expenses", "status": "Pending"},
                        {"name": "Professional services receipts", "status": "Pending"},
                        {"name": "Rent payments", "status": "Pending"},
                        {"name": "Utility bills", "status": "Pending"},
                        {"name": "Insurance payments", "status": "Pending"}
                    ]
                },
                {
                    "category": "Asset Information",
                    "items": [
                        {"name": "Purchases of equipment, furniture, etc.", "status": "Pending"},
                        {"name": "Sales of business assets", "status": "Pending"},
                        {"name": "Depreciation schedules", "status": "Pending"}
                    ]
                },
                {
                    "category": "Employment Documentation",
                    "items": [
                        {"name": f"W-2s and W-3 forms for {tax_filing_year}", "status": "Pending"},
                        {"name": f"1099s issued to contractors for {tax_filing_year}", "status": "Pending"},
                        {"name": f"Payroll tax returns for {tax_filing_year}", "status": "Pending"},
                        {"name": "Benefits and pension plan information", "status": "Pending"}
                    ]
                },
                {
                    "category": "Tax Payments",
                    "items": [
                        {"name": f"Estimated tax payments for {tax_filing_year}", "status": "Pending"},
                        {"name": "Prior year tax returns", "status": "Pending"}
                    ]
                }
            ]
            
            # Add filing deadline information
            filing_deadlines = {
                "S Corporation": {
                    "form": "Form 1120-S",
                    "deadline": f"March 15, {current_year}",
                    "extension_form": "Form 7004",
                    "extension_deadline": f"September 15, {current_year}"
                },
                "C Corporation": {
                    "form": "Form 1120",
                    "deadline": f"April 15, {current_year}",
                    "extension_form": "Form 7004",
                    "extension_deadline": f"October 15, {current_year}"
                },
                "Partnership": {
                    "form": "Form 1065",
                    "deadline": f"March 15, {current_year}",
                    "extension_form": "Form 7004",
                    "extension_deadline": f"September 15, {current_year}"
                },
                "Sole Proprietorship": {
                    "form": "Schedule C (Form 1040)",
                    "deadline": f"April 15, {current_year}",
                    "extension_form": "Form 4868",
                    "extension_deadline": f"October 15, {current_year}"
                },
                "LLC (Single-Member)": {
                    "form": "Schedule C (Form 1040)",
                    "deadline": f"April 15, {current_year}",
                    "extension_form": "Form 4868",
                    "extension_deadline": f"October 15, {current_year}"
                },
                "LLC (Multi-Member)": {
                    "form": "Form 1065",
                    "deadline": f"March 15, {current_year}",
                    "extension_form": "Form 7004",
                    "extension_deadline": f"September 15, {current_year}"
                }
            }
            
            # Determine company type - in a real implementation, this would be stored in the config
            # For now, use a placeholder or default
            company_type = "C Corporation"  # Example
            
            # Ensure the company type is valid and has filing information
            if company_type not in filing_deadlines:
                cfo_logger.warning(f"Unknown company type: {company_type}. Using C Corporation as default.")
                company_type = "C Corporation"
            
            result = {
                "tax_filing_year": tax_filing_year,
                "company_name": self.company_name,
                "company_tax_id": self.company_tax_id,
                "company_type": company_type,
                "filing_information": filing_deadlines.get(company_type, {}),
                "checklist": checklist,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "notes": "This checklist is a general guide. Consult with a tax professional for specific requirements."
            }
            
            return result
            
        except Exception as e:
            cfo_logger.error(f"Error preparing tax filing checklist: {str(e)}")
            # Return minimal valid structure to avoid breaking UI
            return {
                "tax_filing_year": datetime.now().year - 1,
                "company_name": self.company_name,
                "company_tax_id": self.company_tax_id,
                "company_type": "Corporation",
                "filing_information": {
                    "form": "Form 1120",
                    "deadline": f"April 15, {datetime.now().year}",
                    "extension_form": "Form 7004",
                    "extension_deadline": f"October 15, {datetime.now().year}"
                },
                "checklist": [{"category": "Error", "items": [{"name": "Error generating checklist", "status": "Error"}]}],
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "notes": "Error generating tax filing checklist. Please try again.",
                "error": str(e)
            } 