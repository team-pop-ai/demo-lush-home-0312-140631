import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import anthropic

app = FastAPI(title="Lush Home RFP Co-pilot")
templates = Jinja2Templates(directory=".")

# Load mock data with error handling
def load_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

# Initialize data
projects_data = load_json('data/fallback.json', {})
PROJECTS = projects_data.get('projects', [])
SUBCONTRACTORS = projects_data.get('subcontractors', [])
HISTORICAL_BUDGETS = projects_data.get('historical_budgets', [])

# Claude client
anthropic_client = None
if os.environ.get("ANTHROPIC_API_KEY"):
    anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main Teams-style dashboard"""
    # Calculate dashboard metrics
    total_projects = len(PROJECTS)
    active_rfps = sum(1 for p in PROJECTS if p.get('status') == 'rfp_sent')
    quotes_pending = sum(len([s for s in p.get('subcontractors', []) if s.get('quote_status') == 'pending']) 
                        for p in PROJECTS)
    
    # Recent activity feed
    activity_feed = [
        {
            "time": "2 min ago",
            "action": "RFPs sent to 8 subcontractors for Project #47 - Riverside Modern",
            "type": "automation"
        },
        {
            "time": "15 min ago", 
            "action": "Quote received from BuildTech Electrical - $12,400 (within historical range)",
            "type": "quote_received"
        },
        {
            "time": "1 hour ago",
            "action": "Follow-up reminder sent to 3 overdue subcontractors",
            "type": "follow_up"
        },
        {
            "time": "2 hours ago",
            "action": "New project detected in Teams: #48 - Cedar Creek Cabin",
            "type": "new_project"
        }
    ]
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "total_projects": total_projects,
        "active_rfps": active_rfps,
        "quotes_pending": quotes_pending,
        "projects": PROJECTS[:6],  # Show top 6
        "activity_feed": activity_feed
    })

@app.get("/project/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int):
    """Individual project RFP management"""
    project = next((p for p in PROJECTS if p['id'] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return templates.TemplateResponse("project_detail.html", {
        "request": request,
        "project": project,
        "subcontractors": SUBCONTRACTORS
    })

@app.post("/generate_rfp/{project_id}")
async def generate_rfp(project_id: int, request: Request):
    """Generate RFP using Claude API"""
    data = await request.json()
    trade = data.get('trade', '')
    project = next((p for p in PROJECTS if p['id'] == project_id), None)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # If no Claude API key, return sample RFP
    if not anthropic_client:
        sample_rfp = f"""Subject: RFP - {trade} Work for Lush Home Project #{project_id}

Project: {project['name']}
Location: {project['location']}
Completion needed by: {project['target_completion']}

Scope of Work:
• Complete {trade.lower()} installation per architectural plans
• Materials: Contractor to provide all materials unless specified otherwise
• Timeline: Start date TBD, completion 2 weeks from start
• Permits: Contractor responsible for all trade permits

Submission Requirements:
• Itemized quote breakdown showing labor and materials
• Timeline with key milestones
• References from last 3 similar projects
• Current insurance certificate
• Response needed by: {(datetime.now() + timedelta(days=5)).strftime('%m/%d/%Y')}

Contact: RJ Lange, rj@lushhome.com
Phone: (555) 123-4567

Thank you for your prompt attention to this request."""
        
        return JSONResponse({"rfp_content": sample_rfp})
    
    try:
        # Generate RFP with Claude
        system_prompt = """You are an AI assistant helping RJ at Lush Home generate professional RFPs for construction subcontractors. 

Generate a complete, professional RFP email that includes:
- Clear project identification
- Specific scope of work for the trade
- Material responsibility clarification  
- Timeline expectations
- Required submission elements
- Contact information

Keep the tone professional but approachable. Include all essential construction RFP elements."""
        
        user_prompt = f"""Generate an RFP for {trade} work on this project:

Project: {project['name']}
Location: {project['location']}
Target Completion: {project['target_completion']}
Project Description: {project.get('description', 'Prefab home construction')}

Make it specific to {trade} work and include realistic timelines and requirements."""
        
        message = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        rfp_content = message.content[0].text
        
        return JSONResponse({"rfp_content": rfp_content})
        
    except Exception as e:
        # Fallback to sample RFP if Claude fails
        sample_rfp = f"""Subject: RFP - {trade} Work for Lush Home Project #{project_id}

Project: {project['name']}
Location: {project['location']}
Completion needed by: {project['target_completion']}

Scope of Work:
• Complete {trade.lower()} installation per architectural plans
• Materials: Contractor to provide all materials unless specified otherwise  
• Timeline: Start date TBD, completion 2 weeks from start
• Permits: Contractor responsible for all trade permits

Submission Requirements:
• Itemized quote breakdown showing labor and materials
• Timeline with key milestones  
• References from last 3 similar projects
• Current insurance certificate
• Response needed by: {(datetime.now() + timedelta(days=5)).strftime('%m/%d/%Y')}

Contact: RJ Lange, rj@lushhome.com

Thank you for your prompt attention to this request."""
        
        return JSONResponse({"rfp_content": sample_rfp})

@app.post("/send_rfps/{project_id}")
async def send_rfps(project_id: int, request: Request):
    """Simulate sending RFPs to selected subcontractors"""
    data = await request.json()
    selected_subs = data.get('subcontractors', [])
    rfp_content = data.get('rfp_content', '')
    
    # In production, this would integrate with SendGrid
    # For demo, we simulate the send and update project status
    
    project = next((p for p in PROJECTS if p['id'] == project_id), None)
    if project:
        project['status'] = 'rfp_sent'
        project['rfp_sent_date'] = datetime.now().isoformat()
        if 'subcontractors' not in project:
            project['subcontractors'] = []
        
        # Add selected subcontractors to project tracking
        for sub_id in selected_subs:
            sub = next((s for s in SUBCONTRACTORS if s['id'] == sub_id), None)
            if sub:
                project['subcontractors'].append({
                    'id': sub_id,
                    'name': sub['company'],
                    'contact': sub['contact_name'],
                    'email': sub['email'],
                    'trade': sub['specialty'],
                    'quote_status': 'pending',
                    'sent_date': datetime.now().isoformat()
                })
    
    return JSONResponse({
        "success": True, 
        "message": f"RFPs sent to {len(selected_subs)} subcontractors",
        "sent_count": len(selected_subs)
    })

@app.get("/budget_analysis/{project_id}")
async def budget_analysis(project_id: int):
    """Return budget analysis comparing to historical data"""
    project = next((p for p in PROJECTS if p['id'] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Mock budget analysis based on historical data
    analysis = {
        "total_budget_estimate": "$145,000 - $185,000",
        "confidence": "High (based on 12 similar projects)",
        "trade_breakdown": [
            {"trade": "Foundation", "estimate": "$18,000 - $23,000", "status": "normal", "variance": "+5%"},
            {"trade": "Framing", "estimate": "$28,000 - $33,000", "status": "normal", "variance": "-2%"},
            {"trade": "Electrical", "estimate": "$11,000 - $14,000", "status": "normal", "variance": "+1%"},
            {"trade": "Plumbing", "estimate": "$13,000 - $17,000", "status": "high", "variance": "+15%"},
            {"trade": "HVAC", "estimate": "$15,000 - $19,000", "status": "normal", "variance": "+3%"},
            {"trade": "Roofing", "estimate": "$12,000 - $16,000", "status": "normal", "variance": "-1%"},
        ],
        "anomalies": [
            {
                "trade": "Plumbing",
                "issue": "Recent quotes 15% above historical average",
                "recommendation": "Consider reaching out to additional plumbers or review scope"
            }
        ]
    }
    
    return JSONResponse(analysis)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)