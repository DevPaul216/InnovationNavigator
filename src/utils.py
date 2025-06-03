import glob
import io
import json
import os

import requests
import streamlit as st
from googlesearch import search
from openai import OpenAI

from website_parser import get_url_text_and_images


def get_openai_api_key():
    try:
        # Try getting from Streamlit secrets
        return st.secrets["openai_api_key"]
    except (AttributeError, KeyError, FileNotFoundError):
        # Fall back to local JSON file
        try:
            # Construct an absolute path to the keys.json file
            keys_file_path = os.path.join("config", "keys.json")
            with open(keys_file_path) as f:
                config = json.load(f)
            return config["openai_api_key"]
        except Exception as e:
            st.error(f"API key not found. Error: {e}")
            st.stop()


def append_image_messages(image_paths, messages):
    if image_paths is not None:
        for image_path in image_paths:
            messages.append({"role": "user", "content": [
                    {"type": "text", "text": "Please also consider the following image:"},
                    {"type": "image_url","image_url": {"url": image_path,},},
                ],
            })


def make_request(prompt_text, additional_information_list=None, image_paths=None, temperature=1.0, top_p=1.0):
    messages = [
        {"role": "system", "content": prompt_text},
    ]
    if additional_information_list is not None and len(additional_information_list) > 0:
        for additional_information in additional_information_list:
            messages.append({"role": "system", "content": additional_information})
    append_image_messages(image_paths, messages)
    openai_api_key = get_openai_api_key()

    client = OpenAI(api_key=openai_api_key)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=2048
    )
    return completion.choices[0].message.content


def make_request_structured(prompt_text, additional_information_dict=None, image_paths=None, json_schema=None, temperature=1.0, top_p=1.0):
    if additional_information_dict is None:
        additional_information_dict = {}
    messages = [
        {"role": "system", "content": prompt_text},
    ]
    if additional_information_dict is not None and len(additional_information_dict) > 0:
        messages.append({"role": "system", "content": "Please also consider the following pieces of information for this task:"})
        for source, text in additional_information_dict.items():
            additional_information = f"Source: {source}\nContent: {text}"
            messages.append({"role": "user", "content": additional_information}) #changed this from system to user.
    append_image_messages(image_paths, messages)
    openai_api_key = get_openai_api_key()
    client = OpenAI(api_key=openai_api_key)
    if json_schema is None:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=2048
        )
    else:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": json_schema
            },
            temperature=temperature,
            top_p=top_p,
            max_tokens=2048
        )
    return completion.choices[0].message.content


def make_request_image(prompt, model="gpt-image-1", additional_information_dict=None):
    openai_api_key = get_openai_api_key()
    if additional_information_dict is not None and len(additional_information_dict) > 0:
        prompt += "\nPlease also consider the following pieces of information for this task:\n"
        for source, text in additional_information_dict.items():
            additional_information = f"Source: {source}\nContent: {text}"
            prompt += f"{additional_information}\n"
    client = OpenAI(api_key=openai_api_key)
    response = client.images.generate(
        model=model,
        prompt=prompt,
        size="1024x1024",
        quality="low",
        n=1
    )

    if model == "gpt-image-1":
        # gpt-image-1 returns base64-encoded image, not a URL
        import base64
        b64_image = response.data[0].b64_json
        image = io.BytesIO(base64.b64decode(b64_image))
    else:
        url = response.data[0].url
        url_response = requests.get(url)
        image = io.BytesIO(url_response.content)
    return image


def load_prompt(filename_pattern):
    file_paths = glob.glob(f"./canned_prompts/{filename_pattern}.txt")
    if len(file_paths) == 0:
        return None
    with open(file_paths[0], 'r', encoding='utf8') as file:
        # Read the entire content of the file
        return file.read()


def load_schema(filename_pattern):
    file_paths = glob.glob(f"./json_schemas/{filename_pattern}.json")
    if len(file_paths) == 0:
        return None
    with open(file_paths[0], 'r', encoding='utf8') as file:
        # Read the entire content of the file
        return json.load(file)


def scrape_texts(query, num_results):
    texts = {}
    st.subheader("Websites Used")
    for url in search(query, num_results=num_results):
        st.write(url)
        try:
            text, _ = get_url_text_and_images(url)
            texts[url] = text[:15000]
        except Exception as e:
            print("Exception occured during website data fetching:", e)
            print("Ignoring and continuing")
    return texts

def synchronize_shared_elements(data_store, elements_config, template_config):
    """
    Synchronize values of shared elements across all templates/groups that reference them.
    E.g "Pains" is transfered from "Persona" to "Empathy Map" automatically
    """
    # Build a mapping from element name to all (template, group) locations
    element_locations = {}
    for template, tconf in template_config.items():
        # Direct elements
        for element in tconf.get("elements", []):
            if element not in elements_config:
                continue
            econf = elements_config[element]
            if econf.get("type") == "group":
                for group_element in econf.get("elements", []):
                    element_locations.setdefault(group_element, []).append((template, group_element))
            else:
                element_locations.setdefault(element, []).append((template, element))

    # For each shared element, synchronize its value across all locations
    for element, locations in element_locations.items():
        # Find the first non-empty value
        value = None
        for template, el in locations:
            v = data_store.get(template, {}).get(el, [])
            if v:
                value = v
                break
        # Set this value everywhere
        if value is not None:
            for template, el in locations:
                if template in data_store:
                    data_store[template][el] = value