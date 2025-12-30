"""Image handling service."""
from pathlib import Path
from PIL import Image
import io


class ImageHandler:
    """Handle image operations."""

    @staticmethod
    def get_thumbnail(image_data: bytes, size: tuple = (150, 150)) -> Image.Image:
        """Generate thumbnail from image data."""
        try:
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail(size, Image.Resampling.LANCZOS)
            return img
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            return None

    @staticmethod
    def resize_image(image_data: bytes, width: int, height: int) -> Image.Image:
        """Resize image to specified dimensions."""
        try:
            img = Image.open(io.BytesIO(image_data))
            img = img.resize((width, height), Image.Resampling.LANCZOS)
            return img
        except Exception as e:
            print(f"Error resizing image: {e}")
            return None

    @staticmethod
    def convert_to_rgb(image_data: bytes) -> Image.Image:
        """Convert image to RGB mode."""
        try:
            img = Image.open(io.BytesIO(image_data))
            if img.mode != "RGB":
                img = img.convert("RGB")
            return img
        except Exception as e:
            print(f"Error converting image: {e}")
            return None
