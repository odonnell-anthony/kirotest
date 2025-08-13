"""
Templates and automation features service.
"""
import uuid
import logging
import re
import json
from typing import List, Optional, Dict, Any, Set
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import aiohttp

from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.core.exceptions import NotFoundError, ValidationError, InternalError
from app.services.document import DocumentService

logger = logging.getLogger(__name__)


class DocumentTemplate:
    """Document template with metadata and content."""
    def __init__(self, id: str, name: str, description: str, category: str,
                 content_template: str, metadata_template: Optional[Dict[str, Any]] = None,
                 variables: Optional[List[str]] = None, tags: Optional[List[str]] = None):
        self.id = id
        self.name = name
        self.description = description
        self.category = category
        self.content_template = content_template
        self.metadata_template = metadata_template or {}
        self.variables = variables or []
        self.tags = tags or []


class GlossaryTerm:
    """Glossary term with definition and linking rules."""
    def __init__(self, term: str, definition: str, aliases: Optional[List[str]] = None,
                 category: Optional[str] = None, case_sensitive: bool = False,
                 link_url: Optional[str] = None):
        self.term = term
        self.definition = definition
        self.aliases = aliases or []
        self.category = category
        self.case_sensitive = case_sensitive
        self.link_url = link_url


class StaleDocument:
    """Represents a stale document that needs attention."""
    def __init__(self, document_id: uuid.UUID, title: str, last_updated: datetime,
                 days_stale: int, staleness_score: float, reasons: List[str]):
        self.document_id = document_id
        self.title = title
        self.last_updated = last_updated
        self.days_stale = days_stale
        self.staleness_score = staleness_score
        self.reasons = reasons


class TemplatesAutomationService:
    """Service for document templates and automation features."""
    
    # Built-in document templates
    BUILTIN_TEMPLATES = {
        "api_documentation": DocumentTemplate(
            id="api_documentation",
            name="API Documentation",
            description="Template for documenting REST APIs",
            category="API",
            content_template="""# {{api_name}} API Documentation

## Overview
{{api_description}}

## Base URL
```
{{base_url}}
```

## Authentication
{{auth_description}}

## Endpoints

### {{endpoint_name}}
- **Method**: {{http_method}}
- **URL**: `{{endpoint_url}}`
- **Description**: {{endpoint_description}}

#### Request
{{request_example}}

#### Response
{{response_example}}

#### Error Codes
| Code | Description |
|------|-------------|
| 400  | Bad Request |
| 401  | Unauthorized |
| 404  | Not Found |
| 500  | Internal Server Error |

## Rate Limiting
{{rate_limit_info}}

## SDKs and Libraries
{{sdk_info}}

## Changelog
- **{{version}}** ({{date}}): {{changes}}
""",
            variables=["api_name", "api_description", "base_url", "auth_description", 
                      "endpoint_name", "http_method", "endpoint_url", "endpoint_description",
                      "request_example", "response_example", "rate_limit_info", "sdk_info",
                      "version", "date", "changes"],
            tags=["api", "documentation", "rest"]
        ),
        
        "runbook": DocumentTemplate(
            id="runbook",
            name="Operational Runbook",
            description="Template for operational procedures and troubleshooting",
            category="Operations",
            content_template="""# {{service_name}} Runbook

## Service Overview
{{service_description}}

## Architecture
{{architecture_description}}

## Monitoring and Alerts
### Key Metrics
- {{metric_1}}: {{metric_1_description}}
- {{metric_2}}: {{metric_2_description}}
- {{metric_3}}: {{metric_3_description}}

### Alert Thresholds
| Alert | Threshold | Severity |
|-------|-----------|----------|
| {{alert_1}} | {{threshold_1}} | {{severity_1}} |
| {{alert_2}} | {{threshold_2}} | {{severity_2}} |

## Common Issues and Solutions

### Issue: {{issue_1}}
**Symptoms**: {{symptoms_1}}
**Cause**: {{cause_1}}
**Solution**: {{solution_1}}

### Issue: {{issue_2}}
**Symptoms**: {{symptoms_2}}
**Cause**: {{cause_2}}
**Solution**: {{solution_2}}

## Deployment Procedures
### Pre-deployment Checklist
- [ ] {{checklist_item_1}}
- [ ] {{checklist_item_2}}
- [ ] {{checklist_item_3}}

### Deployment Steps
1. {{step_1}}
2. {{step_2}}
3. {{step_3}}

### Rollback Procedures
{{rollback_instructions}}

## Emergency Contacts
- **On-call Engineer**: {{oncall_contact}}
- **Team Lead**: {{team_lead_contact}}
- **Manager**: {{manager_contact}}

## Related Documentation
- [Architecture Diagram]({{architecture_link}})
- [Monitoring Dashboard]({{dashboard_link}})
- [Code Repository]({{repo_link}})
""",
            variables=["service_name", "service_description", "architecture_description",
                      "metric_1", "metric_1_description", "metric_2", "metric_2_description",
                      "metric_3", "metric_3_description", "alert_1", "threshold_1", "severity_1",
                      "alert_2", "threshold_2", "severity_2", "issue_1", "symptoms_1", "cause_1",
                      "solution_1", "issue_2", "symptoms_2", "cause_2", "solution_2",
                      "checklist_item_1", "checklist_item_2", "checklist_item_3",
                      "step_1", "step_2", "step_3", "rollback_instructions",
                      "oncall_contact", "team_lead_contact", "manager_contact",
                      "architecture_link", "dashboard_link", "repo_link"],
            tags=["runbook", "operations", "troubleshooting"]
        ),
        
        "adr": DocumentTemplate(
            id="adr",
            name="Architecture Decision Record (ADR)",
            description="Template for documenting architectural decisions",
            category="Architecture",
            content_template="""# ADR-{{adr_number}}: {{decision_title}}

## Status
{{status}}

## Context
{{context_description}}

## Decision
{{decision_description}}

## Rationale
{{rationale}}

## Consequences
### Positive
- {{positive_consequence_1}}
- {{positive_consequence_2}}

### Negative
- {{negative_consequence_1}}
- {{negative_consequence_2}}

### Neutral
- {{neutral_consequence_1}}

## Alternatives Considered
### Alternative 1: {{alternative_1}}
{{alternative_1_description}}

**Pros**: {{alternative_1_pros}}
**Cons**: {{alternative_1_cons}}

### Alternative 2: {{alternative_2}}
{{alternative_2_description}}

**Pros**: {{alternative_2_pros}}
**Cons**: {{alternative_2_cons}}

## Implementation
{{implementation_details}}

## Monitoring and Success Metrics
- {{metric_1}}: {{metric_1_target}}
- {{metric_2}}: {{metric_2_target}}

## Related Decisions
- [ADR-{{related_adr_1}}]({{related_adr_1_link}})
- [ADR-{{related_adr_2}}]({{related_adr_2_link}})

## References
- [{{reference_1_title}}]({{reference_1_url}})
- [{{reference_2_title}}]({{reference_2_url}})

---
**Date**: {{date}}
**Author**: {{author}}
**Reviewers**: {{reviewers}}
""",
            variables=["adr_number", "decision_title", "status", "context_description",
                      "decision_description", "rationale", "positive_consequence_1",
                      "positive_consequence_2", "negative_consequence_1", "negative_consequence_2",
                      "neutral_consequence_1", "alternative_1", "alternative_1_description",
                      "alternative_1_pros", "alternative_1_cons", "alternative_2",
                      "alternative_2_description", "alternative_2_pros", "alternative_2_cons",
                      "implementation_details", "metric_1", "metric_1_target", "metric_2",
                      "metric_2_target", "related_adr_1", "related_adr_1_link", "related_adr_2",
                      "related_adr_2_link", "reference_1_title", "reference_1_url",
                      "reference_2_title", "reference_2_url", "date", "author", "reviewers"],
            tags=["adr", "architecture", "decision"]
        ),
        
        "user_guide": DocumentTemplate(
            id="user_guide",
            name="User Guide",
            description="Template for user documentation and guides",
            category="Documentation",
            content_template="""# {{product_name}} User Guide

## Introduction
Welcome to {{product_name}}! This guide will help you {{guide_purpose}}.

## Getting Started
### Prerequisites
- {{prerequisite_1}}
- {{prerequisite_2}}
- {{prerequisite_3}}

### Installation
{{installation_instructions}}

### First Steps
1. {{first_step_1}}
2. {{first_step_2}}
3. {{first_step_3}}

## Core Features
### {{feature_1}}
{{feature_1_description}}

**How to use:**
1. {{feature_1_step_1}}
2. {{feature_1_step_2}}
3. {{feature_1_step_3}}

### {{feature_2}}
{{feature_2_description}}

**How to use:**
1. {{feature_2_step_1}}
2. {{feature_2_step_2}}
3. {{feature_2_step_3}}

## Advanced Usage
### {{advanced_feature_1}}
{{advanced_feature_1_description}}

### {{advanced_feature_2}}
{{advanced_feature_2_description}}

## Troubleshooting
### Common Issues
#### {{issue_1}}
**Problem**: {{issue_1_problem}}
**Solution**: {{issue_1_solution}}

#### {{issue_2}}
**Problem**: {{issue_2_problem}}
**Solution**: {{issue_2_solution}}

## FAQ
**Q: {{faq_question_1}}**
A: {{faq_answer_1}}

**Q: {{faq_question_2}}**
A: {{faq_answer_2}}

## Support
- **Documentation**: {{docs_link}}
- **Community**: {{community_link}}
- **Support**: {{support_contact}}

## Changelog
- **{{version}}** ({{date}}): {{changes}}
""",
            variables=["product_name", "guide_purpose", "prerequisite_1", "prerequisite_2",
                      "prerequisite_3", "installation_instructions", "first_step_1",
                      "first_step_2", "first_step_3", "feature_1", "feature_1_description",
                      "feature_1_step_1", "feature_1_step_2", "feature_1_step_3",
                      "feature_2", "feature_2_description", "feature_2_step_1",
                      "feature_2_step_2", "feature_2_step_3", "advanced_feature_1",
                      "advanced_feature_1_description", "advanced_feature_2",
                      "advanced_feature_2_description", "issue_1", "issue_1_problem",
                      "issue_1_solution", "issue_2", "issue_2_problem", "issue_2_solution",
                      "faq_question_1", "faq_answer_1", "faq_question_2", "faq_answer_2",
                      "docs_link", "community_link", "support_contact", "version", "date", "changes"],
            tags=["user-guide", "documentation", "tutorial"]
        )
    }
    
    # Default glossary terms
    DEFAULT_GLOSSARY = {
        "api": GlossaryTerm(
            term="API",
            definition="Application Programming Interface - a set of protocols and tools for building software applications",
            aliases=["Application Programming Interface"],
            category="Technology"
        ),
        "rest": GlossaryTerm(
            term="REST",
            definition="Representational State Transfer - an architectural style for designing networked applications",
            aliases=["RESTful", "Representational State Transfer"],
            category="Architecture"
        ),
        "crud": GlossaryTerm(
            term="CRUD",
            definition="Create, Read, Update, Delete - the four basic operations of persistent storage",
            aliases=["Create Read Update Delete"],
            category="Database"
        ),
        "jwt": GlossaryTerm(
            term="JWT",
            definition="JSON Web Token - a compact, URL-safe means of representing claims between two parties",
            aliases=["JSON Web Token"],
            category="Security"
        ),
        "oauth": GlossaryTerm(
            term="OAuth",
            definition="Open Authorization - an open standard for access delegation",
            aliases=["Open Authorization"],
            category="Security"
        ),
        "microservices": GlossaryTerm(
            term="Microservices",
            definition="An architectural approach where applications are built as a collection of loosely coupled services",
            aliases=["Microservice Architecture"],
            category="Architecture"
        ),
        "docker": GlossaryTerm(
            term="Docker",
            definition="A platform for developing, shipping, and running applications using containerization",
            aliases=["Container", "Containerization"],
            category="DevOps"
        ),
        "kubernetes": GlossaryTerm(
            term="Kubernetes",
            definition="An open-source container orchestration platform for automating deployment, scaling, and management",
            aliases=["K8s", "Container Orchestration"],
            category="DevOps"
        )
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.document_service = DocumentService(db)
        # In-memory storage for demo purposes
        self._custom_templates: Dict[str, DocumentTemplate] = {}
        self._glossary: Dict[str, GlossaryTerm] = self.DEFAULT_GLOSSARY.copy()
    
    async def get_templates(self, category: Optional[str] = None) -> List[DocumentTemplate]:
        """
        Get available document templates.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of document templates
        """
        try:
            all_templates = {**self.BUILTIN_TEMPLATES, **self._custom_templates}
            
            if category:
                return [template for template in all_templates.values() 
                       if template.category.lower() == category.lower()]
            
            return list(all_templates.values())
            
        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return []
    
    async def get_template(self, template_id: str) -> DocumentTemplate:
        """
        Get a specific template by ID.
        
        Args:
            template_id: Template ID
            
        Returns:
            Document template
            
        Raises:
            NotFoundError: If template not found
        """
        try:
            # Check built-in templates first
            if template_id in self.BUILTIN_TEMPLATES:
                return self.BUILTIN_TEMPLATES[template_id]
            
            # Check custom templates
            if template_id in self._custom_templates:
                return self._custom_templates[template_id]
            
            raise NotFoundError(f"Template '{template_id}' not found")
            
        except NotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting template {template_id}: {e}")
            raise InternalError("Failed to get template")
    
    async def create_document_from_template(self, template_id: str, title: str,
                                          variables: Dict[str, str], folder_path: str = "/",
                                          user: User = None) -> Document:
        """
        Create a new document from a template.
        
        Args:
            template_id: Template ID to use
            title: Document title
            variables: Template variable values
            folder_path: Folder path for the document
            user: User creating the document
            
        Returns:
            Created document
        """
        try:
            # Get template
            template = await self.get_template(template_id)
            
            # Replace variables in content
            content = self._replace_template_variables(template.content_template, variables)
            
            # Create document
            from app.schemas.document import DocumentCreateRequest
            
            document_data = DocumentCreateRequest(
                title=title,
                content=content,
                folder_path=folder_path,
                tags=template.tags,
                status=DocumentStatus.DRAFT
            )
            
            document = await self.document_service.create_document(document_data, user)
            
            # Add template metadata
            metadata = document.custom_metadata or {}
            metadata.update({
                "created_from_template": template_id,
                "template_name": template.name,
                "template_variables": variables,
                "created_at": datetime.utcnow().isoformat()
            })
            
            await self.document_service.update_document_metadata(document.id, metadata, user)
            
            logger.info(f"Created document from template {template_id}: {document.id}")
            return document
            
        except (NotFoundError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Error creating document from template: {e}")
            raise InternalError("Failed to create document from template")
    
    async def generate_from_openapi_schema(self, openapi_spec: Dict[str, Any], 
                                         title: str, folder_path: str = "/",
                                         user: User = None) -> Document:
        """
        Generate API documentation from OpenAPI/Swagger schema.
        
        Args:
            openapi_spec: OpenAPI specification
            title: Document title
            folder_path: Folder path for the document
            user: User creating the document
            
        Returns:
            Generated document
        """
        try:
            # Extract information from OpenAPI spec
            info = openapi_spec.get("info", {})
            api_title = info.get("title", "API")
            api_description = info.get("description", "API Documentation")
            api_version = info.get("version", "1.0.0")
            
            servers = openapi_spec.get("servers", [])
            base_url = servers[0].get("url", "https://api.example.com") if servers else "https://api.example.com"
            
            paths = openapi_spec.get("paths", {})
            
            # Generate content
            content = f"""# {api_title} API Documentation

## Overview
{api_description}

**Version**: {api_version}

## Base URL
```
{base_url}
```

## Authentication
{self._extract_auth_info(openapi_spec)}

## Endpoints

"""
            
            # Add endpoints
            for path, methods in paths.items():
                for method, operation in methods.items():
                    if method.upper() in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        content += self._generate_endpoint_docs(path, method.upper(), operation)
            
            # Add schemas if available
            components = openapi_spec.get("components", {})
            schemas = components.get("schemas", {})
            if schemas:
                content += "\n## Data Models\n\n"
                for schema_name, schema_def in schemas.items():
                    content += f"### {schema_name}\n"
                    content += self._generate_schema_docs(schema_def)
                    content += "\n"
            
            # Create document
            from app.schemas.document import DocumentCreateRequest
            
            document_data = DocumentCreateRequest(
                title=title,
                content=content,
                folder_path=folder_path,
                tags=["api", "openapi", "generated"],
                status=DocumentStatus.DRAFT
            )
            
            document = await self.document_service.create_document(document_data, user)
            
            # Add metadata
            metadata = {
                "generated_from": "openapi",
                "openapi_version": openapi_spec.get("openapi", "3.0.0"),
                "api_title": api_title,
                "api_version": api_version,
                "generated_at": datetime.utcnow().isoformat()
            }
            
            await self.document_service.update_document_metadata(document.id, metadata, user)
            
            logger.info(f"Generated API documentation from OpenAPI spec: {document.id}")
            return document
            
        except Exception as e:
            logger.error(f"Error generating from OpenAPI schema: {e}")
            raise InternalError("Failed to generate documentation from OpenAPI schema")
    
    async def detect_stale_documents(self, days_threshold: int = 90) -> List[StaleDocument]:
        """
        Detect stale documents that need attention.
        
        Args:
            days_threshold: Number of days to consider a document stale
            
        Returns:
            List of stale documents
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)
            
            # Query for potentially stale documents
            stmt = select(Document).where(
                and_(
                    Document.status == DocumentStatus.PUBLISHED,
                    Document.updated_at < cutoff_date
                )
            )
            
            result = await self.db.execute(stmt)
            documents = result.scalars().all()
            
            stale_documents = []
            
            for doc in documents:
                days_stale = (datetime.utcnow() - doc.updated_at).days
                staleness_score = self._calculate_staleness_score(doc, days_stale)
                reasons = self._get_staleness_reasons(doc, days_stale)
                
                if staleness_score > 0.5:  # Threshold for considering stale
                    stale_documents.append(StaleDocument(
                        document_id=doc.id,
                        title=doc.title,
                        last_updated=doc.updated_at,
                        days_stale=days_stale,
                        staleness_score=staleness_score,
                        reasons=reasons
                    ))
            
            # Sort by staleness score (highest first)
            stale_documents.sort(key=lambda x: x.staleness_score, reverse=True)
            
            logger.info(f"Detected {len(stale_documents)} stale documents")
            return stale_documents
            
        except Exception as e:
            logger.error(f"Error detecting stale documents: {e}")
            return []
    
    async def add_glossary_term(self, term: str, definition: str, 
                              aliases: Optional[List[str]] = None,
                              category: Optional[str] = None) -> None:
        """
        Add a term to the glossary.
        
        Args:
            term: Term to add
            definition: Term definition
            aliases: Optional aliases
            category: Optional category
        """
        try:
            glossary_term = GlossaryTerm(
                term=term,
                definition=definition,
                aliases=aliases or [],
                category=category
            )
            
            self._glossary[term.lower()] = glossary_term
            logger.info(f"Added glossary term: {term}")
            
        except Exception as e:
            logger.error(f"Error adding glossary term: {e}")
            raise InternalError("Failed to add glossary term")
    
    async def process_glossary_links(self, content: str) -> str:
        """
        Process content to add automatic glossary term links.
        
        Args:
            content: Content to process
            
        Returns:
            Content with glossary links
        """
        try:
            processed_content = content
            
            # Sort terms by length (longest first) to avoid partial matches
            sorted_terms = sorted(self._glossary.items(), 
                                key=lambda x: len(x[1].term), reverse=True)
            
            for term_key, term_obj in sorted_terms:
                # Create pattern for the term and its aliases
                patterns = [re.escape(term_obj.term)]
                patterns.extend([re.escape(alias) for alias in term_obj.aliases])
                
                for pattern in patterns:
                    # Use word boundaries to avoid partial matches
                    if term_obj.case_sensitive:
                        regex_pattern = rf'\b{pattern}\b'
                    else:
                        regex_pattern = rf'\b{pattern}\b'
                        flags = re.IGNORECASE
                    
                    # Replace with markdown link
                    link_text = term_obj.term
                    link_url = term_obj.link_url or f"#glossary-{term_obj.term.lower().replace(' ', '-')}"
                    replacement = f"[{pattern}]({link_url} \"{term_obj.definition}\")"
                    
                    if term_obj.case_sensitive:
                        processed_content = re.sub(regex_pattern, replacement, processed_content)
                    else:
                        processed_content = re.sub(regex_pattern, replacement, processed_content, flags=re.IGNORECASE)
            
            return processed_content
            
        except Exception as e:
            logger.error(f"Error processing glossary links: {e}")
            return content  # Return original content on error
    
    async def get_glossary_terms(self, category: Optional[str] = None) -> List[GlossaryTerm]:
        """
        Get glossary terms.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of glossary terms
        """
        try:
            terms = list(self._glossary.values())
            
            if category:
                terms = [term for term in terms 
                        if term.category and term.category.lower() == category.lower()]
            
            # Sort alphabetically
            terms.sort(key=lambda x: x.term.lower())
            
            return terms
            
        except Exception as e:
            logger.error(f"Error getting glossary terms: {e}")
            return []
    
    def _replace_template_variables(self, template: str, variables: Dict[str, str]) -> str:
        """Replace template variables with actual values."""
        content = template
        
        for var_name, var_value in variables.items():
            placeholder = f"{{{{{var_name}}}}}"
            content = content.replace(placeholder, var_value)
        
        # Replace any remaining placeholders with empty strings or default values
        remaining_placeholders = re.findall(r'\{\{([^}]+)\}\}', content)
        for placeholder in remaining_placeholders:
            content = content.replace(f"{{{{{placeholder}}}}}", f"[{placeholder}]")
        
        return content
    
    def _extract_auth_info(self, openapi_spec: Dict[str, Any]) -> str:
        """Extract authentication information from OpenAPI spec."""
        components = openapi_spec.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        
        if not security_schemes:
            return "No authentication required."
        
        auth_info = []
        for scheme_name, scheme_def in security_schemes.items():
            scheme_type = scheme_def.get("type", "")
            if scheme_type == "http":
                scheme_scheme = scheme_def.get("scheme", "")
                auth_info.append(f"- **{scheme_name}**: HTTP {scheme_scheme.title()}")
            elif scheme_type == "apiKey":
                location = scheme_def.get("in", "")
                name = scheme_def.get("name", "")
                auth_info.append(f"- **{scheme_name}**: API Key in {location} ({name})")
            elif scheme_type == "oauth2":
                auth_info.append(f"- **{scheme_name}**: OAuth 2.0")
        
        return "\n".join(auth_info) if auth_info else "Authentication method not specified."
    
    def _generate_endpoint_docs(self, path: str, method: str, operation: Dict[str, Any]) -> str:
        """Generate documentation for a single endpoint."""
        summary = operation.get("summary", "")
        description = operation.get("description", "")
        
        content = f"""### {method} {path}
{summary}

{description}

"""
        
        # Parameters
        parameters = operation.get("parameters", [])
        if parameters:
            content += "#### Parameters\n"
            content += "| Name | Type | Location | Required | Description |\n"
            content += "|------|------|----------|----------|-------------|\n"
            
            for param in parameters:
                name = param.get("name", "")
                param_type = param.get("schema", {}).get("type", "string")
                location = param.get("in", "")
                required = "Yes" if param.get("required", False) else "No"
                param_desc = param.get("description", "")
                content += f"| {name} | {param_type} | {location} | {required} | {param_desc} |\n"
            
            content += "\n"
        
        # Request body
        request_body = operation.get("requestBody")
        if request_body:
            content += "#### Request Body\n"
            content += f"{request_body.get('description', '')}\n\n"
        
        # Responses
        responses = operation.get("responses", {})
        if responses:
            content += "#### Responses\n"
            for status_code, response in responses.items():
                response_desc = response.get("description", "")
                content += f"- **{status_code}**: {response_desc}\n"
            content += "\n"
        
        content += "---\n\n"
        return content
    
    def _generate_schema_docs(self, schema_def: Dict[str, Any]) -> str:
        """Generate documentation for a schema definition."""
        schema_type = schema_def.get("type", "object")
        description = schema_def.get("description", "")
        
        content = f"{description}\n\n" if description else ""
        
        if schema_type == "object":
            properties = schema_def.get("properties", {})
            required = schema_def.get("required", [])
            
            if properties:
                content += "| Property | Type | Required | Description |\n"
                content += "|----------|------|----------|-------------|\n"
                
                for prop_name, prop_def in properties.items():
                    prop_type = prop_def.get("type", "string")
                    is_required = "Yes" if prop_name in required else "No"
                    prop_desc = prop_def.get("description", "")
                    content += f"| {prop_name} | {prop_type} | {is_required} | {prop_desc} |\n"
        
        return content
    
    def _calculate_staleness_score(self, document: Document, days_stale: int) -> float:
        """Calculate staleness score for a document."""
        base_score = min(days_stale / 365.0, 1.0)  # Normalize to 0-1 based on days
        
        # Adjust based on document characteristics
        metadata = document.custom_metadata or {}
        
        # API docs become stale faster
        if any(tag in ["api", "openapi"] for tag in (metadata.get("tags", []))):
            base_score *= 1.5
        
        # Runbooks and operational docs are critical
        if any(tag in ["runbook", "operations"] for tag in (metadata.get("tags", []))):
            base_score *= 1.3
        
        # Documents with external links may be more prone to staleness
        if "http" in document.content.lower():
            base_score *= 1.2
        
        return min(base_score, 1.0)
    
    def _get_staleness_reasons(self, document: Document, days_stale: int) -> List[str]:
        """Get reasons why a document might be considered stale."""
        reasons = []
        
        if days_stale > 365:
            reasons.append("Not updated in over a year")
        elif days_stale > 180:
            reasons.append("Not updated in over 6 months")
        elif days_stale > 90:
            reasons.append("Not updated in over 3 months")
        
        metadata = document.custom_metadata or {}
        
        # Check for API-related content
        if any(tag in ["api", "openapi"] for tag in (metadata.get("tags", []))):
            reasons.append("API documentation may be outdated")
        
        # Check for version references
        if re.search(r'version\s+\d+\.\d+', document.content.lower()):
            reasons.append("Contains version references that may be outdated")
        
        # Check for external links
        if "http" in document.content.lower():
            reasons.append("Contains external links that may be broken")
        
        # Check for date references
        if re.search(r'\b20\d{2}\b', document.content):
            reasons.append("Contains date references that may be outdated")
        
        return reasons