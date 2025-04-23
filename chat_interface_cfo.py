import openai
import json
import pandas as pd
from datetime import datetime, timedelta
import re
import time
import random
from accounting_engine import AccountingEngine
from tax_module import TaxModule
from config import config
from logger import cfo_logger

class CFOChatInterface:
    """Conversational interface for the CFO Agent.
    
    Provides natural language interaction with financial data and insights.
    """
    
    def __init__(self, accounting_engine=None, tax_module=None):
        """Initialize the CFO chat interface."""
        try:
            self.accounting_engine = accounting_engine or AccountingEngine()
            self.tax_module = tax_module or TaxModule(self.accounting_engine)
            self.openai_api_key = config.openai_api_key
            self.chat_model = config.chat_model
            self.conversation_history = []
            self.fallback_responses = self._init_fallback_responses()
            self.max_retries = 3
            self.retry_delay = 2  # seconds
            
            # Set up OpenAI API key
            if self.openai_api_key:
                openai.api_key = self.openai_api_key
                cfo_logger.info("OpenAI API initialized successfully")
            else:
                cfo_logger.warning("OpenAI API key not set. Chat functionality will be limited to rule-based responses.")
        except Exception as e:
            cfo_logger.error(f"Error initializing chat interface: {str(e)}")
            # Set fallback responses even if initialization fails
            self.fallback_responses = self._init_fallback_responses()
        
    def _init_fallback_responses(self):
        """Initialize fallback responses for different intents."""
        return {
            "cash_balance": [
                "I don't have current cash balance information. Please refresh financial data first.",
                "The cash balance information is not available at the moment.",
                "I need updated financial data to provide the current cash balance."
            ],
            "profit_loss": [
                "I can't provide profit and loss information without current financial data.",
                "To generate a profit and loss report, I need access to up-to-date financial records.",
                "Please refresh the financial data to view profit and loss information."
            ],
            "balance_sheet": [
                "I need updated financial data to generate a balance sheet.",
                "Balance sheet information is not available currently.",
                "Please refresh the financial data first to view the balance sheet."
            ],
            "ar_report": [
                "I don't have current accounts receivable information.",
                "Please refresh financial data to view outstanding invoices.",
                "Accounts receivable data is not available at the moment."
            ],
            "ap_report": [
                "I need current financial data to provide accounts payable information.",
                "Please refresh the data to view outstanding bills.",
                "Accounts payable information is not currently available."
            ],
            "tax_estimate": [
                "I need current financial data to provide tax estimates.",
                "Tax estimation requires up-to-date financial records.",
                "Please refresh financial data first to get tax estimates."
            ],
            "cash_forecast": [
                "Cash flow forecasting requires current financial data.",
                "I can't provide a forecast without updated financial information.",
                "Please refresh financial data first to get a cash flow forecast."
            ],
            "expense_analysis": [
                "I need current financial data to perform expense analysis.",
                "Please refresh financial data to view expense information."
            ],
            "revenue_analysis": [
                "I need current financial data to perform revenue analysis.",
                "Please refresh financial data to view revenue information."
            ],
            "tax_deductions": [
                "I need current financial data to provide tax deductions information.",
                "Please refresh financial data to view tax deductions."
            ]
        }
        
    def get_financial_context(self):
        """Get current financial context to enhance chat responses."""
        try:
            context = {}
            
            # Get KPIs
            kpis = self.accounting_engine.get_financial_kpis()
            if kpis:
                context["kpis"] = {
                    "cash_on_hand": kpis.get("cash_on_hand", 0),
                    "accounts_receivable": kpis.get("accounts_receivable", 0),
                    "accounts_payable": kpis.get("accounts_payable", 0),
                    "revenue_30d": kpis.get("revenue_30d", 0),
                    "expenses_30d": kpis.get("expenses_30d", 0),
                    "net_income_30d": kpis.get("net_income_30d", 0),
                    "profit_margin_30d": kpis.get("profit_margin_30d")
                }
            
            # Get recent invoices (unpaid)
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                invoices = self.accounting_engine.qb_api.get_invoices(start_date, today)
                unpaid_invoices = []
                
                for invoice in invoices.get("QueryResponse", {}).get("Invoice", []):
                    if invoice.get("Balance", 0) > 0:
                        unpaid_invoices.append({
                            "invoice_number": invoice.get("DocNumber", ""),
                            "customer": invoice.get("CustomerRef", {}).get("name", ""),
                            "amount": invoice.get("Balance", 0),
                            "due_date": invoice.get("DueDate", "")
                        })
                
                context["unpaid_invoices"] = unpaid_invoices[:5]  # Limit to 5 most recent
                context["total_unpaid_invoices"] = sum(invoice["amount"] for invoice in unpaid_invoices)
            except Exception as e:
                cfo_logger.error(f"Error getting recent invoices for context: {str(e)}")
            
            # Get upcoming tax payments
            try:
                tax_estimate = self.tax_module.calculate_estimated_taxes()
                upcoming_payments = []
                
                if tax_estimate:
                    for payment in tax_estimate.get("payment_schedule", []):
                        if payment.get("status") == "Upcoming":
                            upcoming_payments.append({
                                "quarter": payment.get("quarter"),
                                "due_date": payment.get("due_date"),
                                "amount": payment.get("amount")
                            })
                else:
                    cfo_logger.warning("No tax estimate data available for context")
                
                context["upcoming_tax_payments"] = upcoming_payments
            except Exception as e:
                cfo_logger.error(f"Error getting tax payment info for context: {str(e)}")
            
            # Get cash flow forecast
            try:
                forecast = self.accounting_engine.forecast_cash_flow(months_ahead=3)
                if forecast:
                    context["cash_flow_forecast"] = [
                        {
                            "period": month.get("period"),
                            "ending_cash": month.get("ending_cash")
                        }
                        for month in forecast
                    ]
            except Exception as e:
                cfo_logger.error(f"Error getting cash flow forecast for context: {str(e)}")
            
            return context
            
        except Exception as e:
            cfo_logger.error(f"Error building financial context: {str(e)}")
            return {}
            
    def identify_intent(self, user_message):
        """Identify the intent of the user's message."""
        message_lower = user_message.lower()
        
        # Define patterns for common intents
        intent_patterns = {
            "cash_balance": [r"cash.*balance", r"how much cash", r"cash on hand", r"available cash"],
            "profit_loss": [r"profit.*loss", r"p&l", r"profit and loss", r"income statement"],
            "balance_sheet": [r"balance sheet", r"assets.*liabilities", r"company worth"],
            "ar_report": [r"accounts receivable", r"unpaid invoices", r"who owes", r"outstanding invoices"],
            "ap_report": [r"accounts payable", r"bills to pay", r"outstanding bills", r"what do we owe"],
            "tax_estimate": [r"tax.*estimate", r"estimated taxes", r"tax payment", r"tax liability"],
            "cash_forecast": [r"forecast", r"projection", r"future cash", r"cash.*forecast"],
            "expense_analysis": [r"expense.*analysis", r"spending", r"where.*money.*going", r"cost breakdown"],
            "revenue_analysis": [r"revenue.*analysis", r"sales.*analysis", r"income.*source", r"where.*money.*coming"],
            "tax_deductions": [r"tax deduction", r"write[ -]offs", r"tax.*saving", r"reduce.*tax"]
        }
        
        # Check for matches
        for intent, patterns in intent_patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower):
                    return intent
        
        # Default to general inquiry if no specific intent is identified
        return "general_inquiry"
        
    def generate_response(self, user_message, refresh_data=False):
        """Generate a response to the user's message."""
        try:
            # Refresh financial data if requested
            if refresh_data:
                self.accounting_engine.refresh_data()
            
            # Get current financial context
            financial_context = self.get_financial_context()
            
            # Identify intent
            intent = self.identify_intent(user_message)
            
            # Add user message to conversation history
            self.conversation_history.append({"role": "user", "content": user_message})
            
            # Generate response based on intent
            if not self.openai_api_key:
                response = self._generate_rule_based_response(intent, financial_context)
            else:
                response = self._generate_llm_response(user_message, intent, financial_context)
            
            # Add response to conversation history
            self.conversation_history.append({"role": "assistant", "content": response})
            
            return response
            
        except Exception as e:
            cfo_logger.error(f"Error generating chat response: {str(e)}")
            return "I'm sorry, I encountered an error while processing your request. Please try again later."
            
    def _generate_rule_based_response(self, intent, context):
        """Generate a rule-based response when API key is not available."""
        kpis = context.get("kpis", {})
        
        if intent == "cash_balance":
            cash = kpis.get("cash_on_hand", 0)
            return f"The current cash balance is ${cash:,.2f}."
            
        elif intent == "profit_loss":
            revenue = kpis.get("revenue_30d", 0)
            expenses = kpis.get("expenses_30d", 0)
            net_income = kpis.get("net_income_30d", 0)
            return f"In the last 30 days, we had revenue of ${revenue:,.2f}, expenses of ${expenses:,.2f}, resulting in net income of ${net_income:,.2f}."
            
        elif intent == "ar_report":
            total_ar = kpis.get("accounts_receivable", 0)
            return f"The current accounts receivable balance is ${total_ar:,.2f}."
            
        elif intent == "ap_report":
            total_ap = kpis.get("accounts_payable", 0)
            return f"The current accounts payable balance is ${total_ap:,.2f}."
            
        elif intent == "cash_forecast":
            forecast = context.get("cash_flow_forecast", [])
            if forecast:
                forecast_text = ", ".join([f"{month['period']}: ${month['ending_cash']:,.2f}" for month in forecast])
                return f"Cash flow forecast for the next 3 months: {forecast_text}."
            else:
                return "I don't have enough data to generate a cash flow forecast at this time."
                
        else:
            return "I understand you're asking about financial information. To provide a more detailed response, please set up the OpenAI API key in the configuration."
            
    def _generate_llm_response(self, user_message, intent, context):
        """Generate a response using OpenAI's language model."""
        try:
            # Format financial context as text
            context_text = self._format_context_for_prompt(context)
            
            # Create system message with financial context and CFO persona
            system_message = f"""You are an experienced Chief Financial Officer (CFO) providing financial insights and guidance to the company. 
You have access to the following current financial information:

{context_text}

As a CFO, you should:
1. Provide clear, concise answers based on the financial data provided
2. Analyze trends and offer strategic recommendations when appropriate
3. Be proactive about financial risks and opportunities
4. Use precise financial terminology but explain concepts when needed
5. Provide specific numbers from the data when answering quantitative questions
6. When forecasting or making predictions, clearly indicate the assumptions and limitations
7. If you don't have specific data to answer a question, acknowledge this and suggest what information would be helpful

Your tone should be professional, confident, and analytical while remaining conversational and accessible.
"""

            # Prepare conversation for API
            messages = [
                {"role": "system", "content": system_message}
            ]
            
            # Add relevant conversation history (last 5 exchanges)
            if len(self.conversation_history) > 0:
                history_to_include = self.conversation_history[-min(10, len(self.conversation_history)):]
                messages.extend(history_to_include)
                
            # Add current user message if not already included
            if not any(msg.get("content") == user_message and msg.get("role") == "user" for msg in messages):
                messages.append({"role": "user", "content": user_message})
            
            # Call OpenAI API
            response = openai.ChatCompletion.create(
                model=self.chat_model,
                messages=messages,
                temperature=0.4,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            cfo_logger.error(f"Error generating LLM response: {str(e)}")
            return f"I encountered an error while generating a response. Please check your API configuration or try again later."
            
    def _format_context_for_prompt(self, context):
        """Format financial context into a text representation for the prompt."""
        text_parts = []
        
        # Format KPIs
        kpis = context.get("kpis", {})
        if kpis:
            text_parts.append("CURRENT FINANCIAL METRICS:")
            text_parts.append(f"- Cash on hand: ${kpis.get('cash_on_hand', 0):,.2f}")
            text_parts.append(f"- Accounts receivable: ${kpis.get('accounts_receivable', 0):,.2f}")
            text_parts.append(f"- Accounts payable: ${kpis.get('accounts_payable', 0):,.2f}")
            text_parts.append(f"- Last 30 days revenue: ${kpis.get('revenue_30d', 0):,.2f}")
            text_parts.append(f"- Last 30 days expenses: ${kpis.get('expenses_30d', 0):,.2f}")
            text_parts.append(f"- Last 30 days net income: ${kpis.get('net_income_30d', 0):,.2f}")
            
            if kpis.get('profit_margin_30d') is not None:
                text_parts.append(f"- Profit margin (30 days): {kpis.get('profit_margin_30d', 0):.2f}%")
            
            text_parts.append("")
        
        # Format unpaid invoices
        unpaid_invoices = context.get("unpaid_invoices", [])
        if unpaid_invoices:
            text_parts.append("RECENT UNPAID INVOICES:")
            for invoice in unpaid_invoices:
                text_parts.append(f"- Invoice #{invoice.get('invoice_number')} | Customer: {invoice.get('customer')} | Amount: ${invoice.get('amount'):,.2f} | Due: {invoice.get('due_date')}")
            text_parts.append(f"Total accounts receivable: ${context.get('total_unpaid_invoices', 0):,.2f}")
            text_parts.append("")
        
        # Format upcoming tax payments
        tax_payments = context.get("upcoming_tax_payments", [])
        if tax_payments:
            text_parts.append("UPCOMING ESTIMATED TAX PAYMENTS:")
            for payment in tax_payments:
                text_parts.append(f"- Q{payment.get('quarter')} | Due: {payment.get('due_date')} | Amount: ${payment.get('amount'):,.2f}")
            text_parts.append("")
        
        # Format cash flow forecast
        forecast = context.get("cash_flow_forecast", [])
        if forecast:
            text_parts.append("CASH FLOW FORECAST:")
            for month in forecast:
                text_parts.append(f"- {month.get('period')}: ${month.get('ending_cash'):,.2f}")
            text_parts.append("")
        
        return "\n".join(text_parts)
    
    def clear_conversation_history(self):
        """Clear the conversation history."""
        self.conversation_history = []
        return "Conversation history cleared." 