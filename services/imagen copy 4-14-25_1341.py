# services/imagen.py
import os
import base64
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai # Keep this import style
from google.generativeai import types

class ImagenClient:
    """Client for interacting with the Google Imagen API."""

    def __init__(self, api_key, model='imagen-3.0-generate-002'):
        if not api_key:
            raise ValueError("Gemini API key is required for ImagenClient.")
        self.api_key = api_key
        self.model_name = model
        try:
            # --- Instantiate the client here ---
            # No need to call genai.configure() if using Client explicitly
            self.client = genai.Client(api_key=self.api_key)
            logging.info(f"ImagenClient initialized using genai.Client for model: {self.model_name}")
            # --- Test connection (Optional but good) ---
            # try:
            #     self.client.models.list() # Make a simple call to check auth
            #     logging.info("Successfully listed models, API key seems valid.")
            # except Exception as list_err:
            #     logging.warning(f"Could not list models during init: {list_err}")
            # --- End Test ---

        except Exception as e:
            logging.error(f"Failed to initialize ImagenClient (genai.Client): {e}")
            raise

    def generate_image_prompt(self, keyword, content_snippet=None):
        # --- THIS METHOD REMAINS UNCHANGED ---
        base_template = f"Create a photorealistic 16:9 image showcasing {keyword}. "
        specifics = ""
        if any(word in keyword.lower() for word in ['chair', 'stool', 'seating']):
             specifics += f"Show a stylish, comfortable {keyword} in a modern man cave setting with ambient lighting. "
        elif any(word in keyword.lower() for word in ['bar', 'counter']):
             specifics += f"Show a well-designed {keyword} with decorative lighting, high-end finishes, and bar accessories. "
        elif any(word in keyword.lower() for word in ['table', 'desk']):
             specifics += f"Show a premium {keyword} made of quality materials in an elegant home office or game room setting. "
        elif any(word in keyword.lower() for word in ['light', 'lamp', 'lighting']):
             specifics += f"Show attractive {keyword} creating a warm ambiance in a stylish entertainment space. "
        elif any(word in keyword.lower() for word in ['decor', 'sign', 'art', 'wall']):
             specifics += f"Show trendy {keyword} displayed in a modern basement or game room with complementary furniture. "
        else:
             specifics += f"Show {keyword} in an upscale home environment with complementary decor and warm lighting. "

        content_details = ""
        if content_snippet and len(content_snippet) > 100:
             words = content_snippet.lower().split()
             descriptive_words = [w for w in words if len(w) > 5 and w not in ["about", "should", "would", "could", "their", "there", "these", "those"]]
             if descriptive_words:
                 selected_words = descriptive_words[:5]
                 content_details = f"Include elements of {', '.join(selected_words)}. "

        quality_instructions = ("Create a clean, professional image with high-quality lighting, proper perspective, "
                               "and realistic textures. No text overlays or watermarks. Suitable as a featured image for a blog post.")

        prompt = base_template + specifics + content_details + quality_instructions
        logging.info(f"Generated image prompt: {prompt}")
        return prompt


    # --- REPLACE THE generate_image METHOD with logic from test script ---
    def generate_image(self, prompt):
        """
        Generates an image using the configured client and model.

        Args:
            prompt (str): The detailed prompt for the image generation.

        Returns:
            BytesIO: Image data in JPEG format if successful, None otherwise.
        """
        if not self.client:
             logging.error("ImagenClient not properly initialized (no client).")
             return None
        try:
            logging.info(f"Calling client.models.generate_images for model: {self.model_name}")

            # Use the exact structure from your working test script
            response = self.client.models.generate_images(
                model=self.model_name, # Use the model name stored during init
                prompt=prompt,
                # Use the types namespace from the import
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9", # Added from original integration code
                    # output_mime_type='image/jpeg' # Optional: Let API default or set if needed
                )
            )

            # Check response structure based on test script logic
            if not hasattr(response, 'generated_images') or not response.generated_images:
                 logging.error("No 'generated_images' found in the API response.")
                 logging.debug(f"Full generate_images Response: {response}")
                 return None

            # Get image bytes (test script confirms this path)
            image_bytes = response.generated_images[0].image.image_bytes
            logging.info(f"Image generated successfully ({len(image_bytes)} bytes).")

            # --- Processing Bytes (same as before) ---
            image_data = BytesIO(image_bytes) # Assume raw bytes first

            try:
                image_data.seek(0)
                img = Image.open(image_data)
                logging.info(f"Image validated: format={img.format}, size={img.size}, mode={img.mode}")

                output_img = BytesIO()
                img_format_to_save = 'JPEG'
                save_kwargs = {'quality': 95}
                if img.mode != 'RGB': # Convert common modes to RGB for JPEG
                    img = img.convert('RGB')
                    logging.info(f"Converted image from {img.mode} to RGB for JPEG saving.")

                img.save(output_img, img_format_to_save, **save_kwargs)
                output_img.seek(0)
                processed_size = len(output_img.getvalue())
                logging.info(f"Processed image as {img_format_to_save}: size={processed_size} bytes")
                return output_img

            except Exception as img_err:
                logging.error(f"Error processing image with PIL: {str(img_err)}")
                image_data.seek(0)
                logging.warning("Falling back to returning unprocessed image data due to PIL error.")
                return image_data # Return raw/decoded bytes if PIL fails

        except Exception as e:
            logging.error(f"Error calling client.models.generate_images: {str(e)}", exc_info=True)
            return None
    # --- End Class ---