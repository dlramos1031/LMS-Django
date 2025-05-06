from django.apps import AppConfig

class BooksConfig(AppConfig):
    """
    App configuration for the 'books' application.
    """
    # Specifies the default type for auto-created primary key fields
    default_auto_field = 'django.db.models.BigAutoField'
    # The name of the application
    name = 'books'

    def ready(self):
        """
        This method is called once Django is ready.
        It's the recommended place to import signals to ensure they are connected.
        """
        print("BooksConfig ready: Importing signals...")
        try:
            # Import the signals module from the current app (.)
            import books.signals
            print("Successfully imported books.signals")
        except ImportError:
            # Handle case where signals.py might not exist (though we just created it)
            print("Could not import books.signals (signals.py might be missing or contain import errors).")
        except Exception as e:
            # Catch any other potential errors during signal import
            print(f"Error importing books.signals: {e}")
