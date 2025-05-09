from rich.text import Text
from textual.app import App
from textual.widgets import ListView, ListItem, Checkbox, Label, Header, Footer, DataTable, Static, Input, Button, ProgressBar
from textual.containers import Container, Center, VerticalScroll
from textual.reactive import reactive
from textual.events import Key
import webbrowser
import asyncio
import os
from app.api_utils import (
    move_to_deletion_folder, scan_directory_for_tickets, fetch_ticket_info,
    error_logger, debug_logger, adjust_path, perm_remove_directory,
    BACKUPS_LOCATION, INSTANCE, DELETION_LOCATION, APPLICATION_PATH
)

class TicketApp(App):
    CSS_PATH = adjust_path(APPLICATION_PATH + "/style.tcss")
    selected_index: reactive[int] = reactive(0)
    ticket_info_list: reactive[list] = reactive([])

    is_deletion_list_created: bool = False

    def compose(self):
        """
        Compose the app layout with all the necessary widgets and containers.

        Yields:
            Container: The main layout containers and widgets.
        """
        yield Header()
        login_container = self.login_container()
        login_container.id = "login_container"
        login_container.classes = "login_container"
        yield login_container

        self.main_table = self.create_table(
            "data_table", [
                "Ticket Number",
                "Folder Name",
                "Size",
                "Closed At (Local)",
                "Closed By Username",
                "Ready for Pickup Tag",
                "Ready for Deletion"
            ]
        )

        self.perm_delete_table = self.create_table(
            "delete_table", [
                "Ticket Number",
                "Folder Name",
                "Size",
                "Closed At (Local)",
                "Closed By Username",
                "Ready for Pickup Tag",
                "Ready for Deletion"
            ]
        )

        self.main_buttons = self.create_container(
            "main_buttons",
            [
                Button("Move to Deletion Folder", id="move_deletion"),
                Button("Empty Delete Folder", id="perm_delete")
            ]
        )
        self.main_buttons.classes = "button_container"

        self.perm_delete_options = self.create_container(
            "perm_delete_options",
            [
                Button("Go Back", id="back_to_main"),
                Button("PERMANENTLY DELETE THESE FILES", id="acutally_delete_files")
            ]
        )
        self.perm_delete_options.classes = "button_container"

        self.main_container = self.create_container(
            "main_container",
            [
                self.main_table,
                self.main_buttons
            ]
        )
        self.main_container.classes = "data_table"
        yield self.main_container

        self.perm_delete_container = self.create_container(
            "delete_container",
            [
                self.perm_delete_table,
                self.perm_delete_options
            ]
        )
        self.perm_delete_container.styles.display = "none"
        self.perm_delete_container.classes = "data_table"
        yield self.perm_delete_container
        
        with Center(id="progress_container"):
            yield Label("Loading Service Now API", id="progress_label")
            yield ProgressBar(id="progress_bar", show_eta=False)

        self.move_to_deletion_folder_container_scroll = VerticalScroll(id="delete_center_container")

        self.move_to_deletion_folder_confirmation_text = Static("Are you sure ALL of these folders are ready to be moved to the 'MARKED FOR DELETION' folder?")
        self.move_to_deletion_folder_confirmation_text.id = "deletion_confirmation_text"
        self.move_to_deletion_folder_container = Container(
            self.move_to_deletion_folder_container_scroll,
            self.move_to_deletion_folder_confirmation_text,
            Container(
                Button("No", id="no_deletion_button", variant="error"),
                Button("Yes", id="yes_deletion_button", variant="success"),
                classes="button_container"
            )
        )
        self.move_to_deletion_folder_container.id = "move_to_deletion_folder_container"
        self.move_to_deletion_folder_container.styles.display = "none" 
        yield self.move_to_deletion_folder_container
     
        #login_error = Static("Incorrect Username or Password. Quit application and try again")
        #login_error.id = "login_error"
        #yield login_error
        
        self.title = 'HDCS Backup Management Utility'

        bottom_row = Static("Ctrl+Q to quit | Enter to open ticket in browser | Tab and arrow keys to navigate", classes="bold foot_info")
        bottom_row.styles.text_align = "center"

        yield self.create_container("test", [bottom_row])

        # yield bottom_row
        yield Footer()

    def create_table(self, id, columns) -> DataTable:
        """
        Creates data table widget

        Args:
            id (str): ID for new table
            columns ([str]): List of columns for the new table
        """
        table = DataTable(id=id)
        table.add_columns(*columns)
        table.cursor_type = "row"
        return table
    
    def create_container(self, id, widgets) -> Container:
        """
        Create container widget to hold other widgets

        Args:
            id (str): #ID of container
        """
        container = Container(*widgets)
        container.id = id

        return container

    def login_container(self) -> Container:
        """
        Create the login container with input fields for username and password.

        Returns:
            Container: The login container with input fields and login button.
        """
        return Container(
            Static(f"ServiceNow Instance: {INSTANCE}", classes="bold"),
            Static("Username:", classes="bold"),
            Input(id="username", placeholder="Username"),
            Static("Password:", classes="bold"),
            Input(id="password", placeholder="Password", password=True),
            Button("Login", id="login_button")
        )
    
    def show(self, id) -> None:
        """
        Method to change display of Textual Widget to 'block'

        Args:
            id (str): String of the ID of a certain widget
        """
        self.query_one(id).styles.display = "block"
    
    def hide(self, id) -> None:
        """
        Method to change display of Textual Widget to 'none'

        Args:
            id (str): String of the ID of a certain widget
        """
        self.query_one(id).styles.display = "none"

    def on_mount(self) -> None:
        """
        Method called when the app is mounted. Initialize and display the main table and progress bar.
        """
        #self.show("#data_table")
        self.query_one("#username").focus()
        self.show("#login_container")
        self.hide("#main_container")
        self.hide("#progress_container")
        self.hide("#move_to_deletion_folder_container")
        #self.hide("#login_error")

        # Set default theme for app
        self.theme = "monokai"

    async def login_button_press(self) -> None:
        self.hide("#login_container")
        self.hide("#main_container")
        self.show("#progress_container")
        self.username = self.query_one("#username").value
        self.password = self.query_one("#password").value
        await self.load_tickets(INSTANCE, self.username, self.password, BACKUPS_LOCATION, self.main_table)
        self.show("#main_container")
        self.query_one("#data_table").focus()

    async def no_move_delete_button_press(self) -> None:
        self.show("#main_container")
        self.hide("#move_to_deletion_folder_container")
        self.query_one("#data_table").focus()
        # Remove checkboxes after exiting screen
        await self.move_to_deletion_folder_container_scroll.remove_children('*')

    async def yes_move_deletion_button_press(self) -> None:
        ticket_numbers = [ checkbox.id.split("_")[1] for checkbox in self.query('Checkbox') if checkbox.value ]
        
        debug_logger.debug(f"MOVE TO DELETION FOLDER: {ticket_numbers}")

        move_to_deletion_folder(ticket_numbers)

        for ticket in ticket_numbers:
            self.notify(message="Moved to 'Ready for Deletion' folder", title=f"{ticket}: Moved.")
        await self.load_tickets(INSTANCE, self.username, self.password, BACKUPS_LOCATION, self.main_table)
        self.show("#main_container")
        self.query_one("#data_table").focus()
        self.hide("#move_to_deletion_folder_container")
        # Remove checkboxes after exiting screen
        await self.move_to_deletion_folder_container_scroll.remove_children('*')

    def move_deletion_press(self) -> None:
        self.show("#move_to_deletion_folder_container")
        self.hide("#main_container")
        self.show_move_deletion_confirmation()

    async def perm_delete_press(self) -> None:
        await self.load_tickets(INSTANCE, self.username, self.password, DELETION_LOCATION, self.perm_delete_table)
        self.hide('#' + self.main_container.id)
        self.show('#' + self.perm_delete_container.id)

    async def back_to_main(self) -> None:
        #self.show('#' + self.main_container.id)
        self.hide('#' + self.perm_delete_container.id)
        await self.load_tickets(INSTANCE, self.username, self.password, BACKUPS_LOCATION, self.main_table)
        self.show('#' + self.main_container.id)

    def acutally_delete_files_press(self) -> None:
        deletion_folders = os.listdir(os.path.abspath(DELETION_LOCATION))
        for folder in deletion_folders:
            self.perm_removal_progress(folder, len(deletion_folders))
            is_deletion_complete = perm_remove_directory(folder)

            if is_deletion_complete:
                self.notify(message="Selected files permanently deleted.", title=f"{folder}: Done.", severity="information", timeout=15)
            else:
                self.notify(message="Error during deletion process.", title=f"{folder} Failed.", severity="error", timeout=15)

        self.hide('#' + self.perm_delete_container.id)
        self.hide('#progress_container')
        self.show('#main_container')

    async def on_button_pressed(self, event) -> None:
        """
        Handle button pressed events, including login, deletion confirmation, and cancellation.

        Args:
            event (Button.Pressed): The button pressed event.
        """
        if event.button.id == "login_button":
            await self.login_button_press()
        elif event.button.id == "no_deletion_button":
            await self.no_move_delete_button_press()
        elif event.button.id == "yes_deletion_button":
            await self.yes_move_deletion_button_press()
        elif event.button.id == "move_deletion":
            self.move_deletion_press()
        elif event.button.id == "perm_delete":
            await self.perm_delete_press()
        elif event.button.id == "back_to_main":
            await self.back_to_main()
        elif event.button.id == "acutally_delete_files":
            self.acutally_delete_files_press()

    async def fetch_ticket_info_task(self, instance, username, password, ticket_number) -> None:
        """
        Fetch information for a specific ticket asynchronously and update the progress.

        Args:
            instance (str): ServiceNow instance.
            username (str): Username for authentication.
            password (str): Password for authentication.
            ticket_number (str): Ticket number.
        """
        try:
            ticket_info = await asyncio.to_thread(fetch_ticket_info, instance, username, password, ticket_number)
            if ticket_info:
                debug_logger.debug(f"ticket_info is {ticket_info}")
                self.ticket_info_list.append(ticket_info)
                #self.call_later(self.update_progress)
                self.update_progress(ticket_number)
                return True
            else:
                return False
        except Exception as e:
            #self.show("#login_error")
            self.hide("#main_container")
            #self.query_one("#login_error").styles.color = "red"
            self.hide("#progress_bar")
            self.show("#login_container")
            self.notify(message="Failed login.", title="Error", severity="error")
            error_logger.error(f"Error fetching ticket info: {e}")
            return False
    
    def update_progress(self, ticket_number, label_text="Loaded") -> None:
        """
        Update the progress bar by advancing its value.
        """
        progress = self.query_one("#progress_bar")
        label = self.query_one("#progress_label")
        label.update(f"{label_text} {ticket_number}...")
        label.recompose()
        progress.advance(1)

    def reset_progress_bar(self, max):
        self.show("#progress_container")
        progress = self.query_one("#progress_bar")
        progress.progress = 0
        progress.recompose()
        progress.total = max

    def perm_removal_progress(self, current, max):
        self.show("#progress_container")
        progress = self.query_one("#progress_bar")
        progress.progress = 0
        progress.total = max
        progress.recompose()
        self.update_progress(current, "Deleting")

    async def load_tickets(self, instance, username, password, directory, table) -> None:
        """
        Load ticket information for all tickets in the backups location.

        Args:
            instance (str): ServiceNow instance.
            username (str): Username for authentication.
            password (str): Password for authentication.
            directory (str): Directory of backup folders.
            table (DataTable): DataTable widget to populate with data.
        """
        ticket_numbers = scan_directory_for_tickets(directory)
        self.ticket_info_list = []
        total_tickets = len(ticket_numbers)
        
        self.reset_progress_bar(total_tickets)

        tasks = []

        try:
            for ticket_number in ticket_numbers:
                task = asyncio.create_task(self.fetch_ticket_info_task(instance, username, password, ticket_number))

                tasks.append(task)
            
            await asyncio.gather(*tasks)

            if all(list(map(lambda task: task.result(), tasks))):
                await self.populate_table(table)
            else:
                self.hide("#main_container")
                self.show("#login_container")
                error_logger.error(f"Login error for user {username}")
                self.notify(message="Failed login/authentication with Service-Now.", title="Error", severity="error")
        except Exception as e:
            self.hide("#main_container")
            self.show("#login_container")
            error_logger.error(f"Exception raised during login: {e}")
            self.notify(message="Failed login/authentication with Service-Now.", title="Error", severity="error")
    
    async def populate_table(self, table) -> None:
        """
        Populate the data table with the fetched ticket information.
        """
        table.clear()
        for info in self.ticket_info_list:
            row_style = ''
            if info['ready_for_deletion']:
                row_style = "bold"
            table.add_row(
                Text(info['ticket_number']),
                Text(info['folder_name']),
                Text(str(info['folder_size'])),
                Text(info['closed_at_local'], style=row_style),
                Text(info['closed_by_username'], style=row_style),
                Text(str(info['has_ready_for_pickup_tag']), style=row_style),
                Text(str(info['ready_for_deletion']), style=row_style)
            )
        self.show('#' + table.id)
        self.hide("#progress_container")
        self.notify(message="Ticket info loaded.", title="Done.", severity="information", timeout=5)

    def create_marked_for_delete_checklist(self, deletion_info_list) -> None:

        self.move_to_deletion_folder_container_scroll.recompose()

        # Adds checkboxes to select which folders to delete
        for info in deletion_info_list:
            self.move_to_deletion_folder_container_scroll.mount(
                Checkbox(
                    f"Name: {info['folder_name']} | Closed: {info['closed_at_local']} | Closed by: {info['closed_by_username']}",
                    classes="deletion_queue",
                    id=f"checkbox_{info['ticket_number']}"
                )
            )

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """
        Handle the event when a row is selected in the data table.

        Args:
            event (DataTable.RowSelected): The data table row selected event.
        """
        selected_index = event.cursor_row
        selected_row = self.ticket_info_list[selected_index]
        url = selected_row['url']
        webbrowser.open(url)

    def show_move_deletion_confirmation(self) -> None:
        """
        Display the move to deletion folder confirmation container with the list of folders ready for deletion.
        """
        deletion_info_list = [info for info in self.ticket_info_list if info['ready_for_deletion']]
        
        if not deletion_info_list:
            self.move_to_deletion_folder_confirmation_text.update("No tickets are ready for deletion.")
            self.move_to_deletion_folder_confirmation_text.recompose()
        else:
            self.create_marked_for_delete_checklist(deletion_info_list)
            self.move_to_deletion_folder_confirmation_text.update("Are you sure ALL of these folders are ready to be moved to the 'MARKED FOR DELETION' folder?")
            self.move_to_deletion_folder_confirmation_text.recompose()
        self.hide("#main_container")
        self.show('#' + self.move_to_deletion_folder_container_scroll.id)
