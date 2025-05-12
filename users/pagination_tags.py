from django import template
from urllib.parse import urlencode

register = template.Library()

@register.simple_tag
def query_transform(request_get, **kwargs):
    updated = request_get.copy()
    for k, v in kwargs.items():
        if v is not None:
            updated[k] = v
        else:
            updated.pop(k, None) # Remove if value is None

    # Ensure 'page' is handled correctly or removed if we are setting it
    if 'page' in kwargs and kwargs['page'] is None : # If explicitly removing page for some link
        updated.pop('page', None)
    elif 'page' not in kwargs and 'page' in updated: # If building links for other params, keep current page
        pass # Keep existing page if not explicitly changing it

    return updated.urlencode()

@register.simple_tag
def get_params_excluding_page(request_get):
    params = request_get.copy()
    params.pop('page', None) # Remove 'page' if it exists
    return params.urlencode()