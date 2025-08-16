#!/usr/bin/env python3
"""
Focus Session CLI - A mindful productivity tool
"""
import os
import sys
import time
import select
import termios
import tty
import warnings
from pathlib import Path

# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# Suppress plyer warnings
warnings.filterwarnings("ignore", category=UserWarning, module="plyer")

import pygame
from plyer import notification
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live


console = Console()


class AudioPlayer:
    """Handles audio playback with pygame mixer"""
    
    def __init__(self):
        pygame.mixer.init()
        self.is_muted = False
        self.saved_volume = 1.0
        
    def play(self, file_path, loop=False):
        """Play an audio file"""
        pygame.mixer.music.load(file_path)
        loops = -1 if loop else 0
        pygame.mixer.music.play(loops=loops)
        
    def stop(self):
        """Stop current playback"""
        pygame.mixer.music.stop()
        
    def pause(self):
        """Pause current playback"""
        pygame.mixer.music.pause()
        
    def unpause(self):
        """Resume playback"""
        pygame.mixer.music.unpause()
        
    def toggle_mute(self):
        """Toggle mute state"""
        if self.is_muted:
            pygame.mixer.music.set_volume(self.saved_volume)
            self.is_muted = False
        else:
            self.saved_volume = pygame.mixer.music.get_volume()
            pygame.mixer.music.set_volume(0)
            self.is_muted = True
        return self.is_muted
        
    def is_playing(self):
        """Check if audio is currently playing"""
        return pygame.mixer.music.get_busy()
        
    def get_position(self):
        """Get current position in milliseconds"""
        return pygame.mixer.music.get_pos()


class KeyboardInput:
    """Non-blocking keyboard input handler for terminal"""
    
    def __init__(self):
        self.old_settings = None
        
    def __enter__(self):
        if sys.platform != 'win32':
            self.old_settings = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())
        return self
        
    def __exit__(self, type, value, traceback):
        if sys.platform != 'win32' and self.old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.old_settings)
            
    def get_key(self, timeout=0.1):
        """Get a single keypress with timeout"""
        if sys.platform == 'win32':
            import msvcrt
            start_time = time.time()
            while time.time() - start_time < timeout:
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key in [b'\x00', b'\xe0']:  # Special keys
                        msvcrt.getch()  # Consume second byte
                        return None
                    return key.decode('utf-8', errors='ignore').lower()
                time.sleep(0.01)
            return None
        else:
            # Unix/Linux/macOS
            if sys.stdin in select.select([sys.stdin], [], [], timeout)[0]:
                key = sys.stdin.read(1)
                return key.lower()
            return None


class FocusSession:
    """Manages the focus session with timer and controls"""
    
    def __init__(self, duration_minutes, audio_player):
        self.duration = duration_minutes * 60  # Convert to seconds
        self.audio_player = audio_player
        self.is_paused = False
        self.session_active = True
        self.time_remaining = self.duration
        self.last_update = time.time()
        
    def toggle_pause(self):
        """Toggle pause state"""
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.audio_player.pause()
        else:
            self.audio_player.unpause()
            self.last_update = time.time()
        return self.is_paused
        
    def update_timer(self):
        """Update remaining time if not paused"""
        if not self.is_paused and self.session_active:
            current_time = time.time()
            elapsed = current_time - self.last_update
            self.time_remaining -= elapsed
            self.last_update = current_time
            
            if self.time_remaining <= 0:
                self.session_active = False
                self.time_remaining = 0
                
    def get_progress_string(self):
        """Get formatted time remaining"""
        minutes = int(self.time_remaining // 60)
        seconds = int(self.time_remaining % 60)
        return f"{minutes:02d}:{seconds:02d}"
        
    def get_progress_percentage(self):
        """Get progress as percentage"""
        elapsed = self.duration - self.time_remaining
        return (elapsed / self.duration) * 100 if self.duration > 0 else 100
        
    def is_complete(self):
        """Check if session is complete"""
        return not self.session_active


class MeditationPlayer:
    """Handles meditation playback with progress bar"""
    
    def __init__(self, audio_player, file_path):
        self.audio_player = audio_player
        self.file_path = file_path
        self.skip_requested = False
        self.is_paused = False
        
    def play_with_progress(self):
        """Play meditation with progress bar and controls"""
        # Load the audio to get duration
        sound = pygame.mixer.Sound(self.file_path)
        duration_ms = sound.get_length() * 1000
        
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]🧘 Meditation Session[/bold cyan]\n\n"
            "[dim]Press [bold]SPACE[/bold] to pause/resume • [bold]S[/bold] to skip[/dim]",
            border_style="cyan"
        ))
        console.print()
        
        # Start playback
        self.audio_player.play(self.file_path)
        
        # Progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=60),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Meditation Progress", total=100)
            start_time = time.time()
            elapsed_time = 0
            
            with KeyboardInput() as kb:
                while (self.audio_player.is_playing() or self.is_paused) and not self.skip_requested:
                    # Check for keyboard input
                    key = kb.get_key(0.1)
                    if key == ' ':
                        self.is_paused = not self.is_paused
                        if self.is_paused:
                            self.audio_player.pause()
                            progress.update(task, description="[yellow]Meditation Progress (Paused)")
                        else:
                            self.audio_player.unpause()
                            progress.update(task, description="[cyan]Meditation Progress")
                    elif key == 's':
                        self.skip_requested = True
                        break
                    
                    if not self.is_paused:
                        current_time = time.time()
                        elapsed_time = (current_time - start_time) * 1000
                        percentage = min((elapsed_time / duration_ms) * 100, 100)
                        progress.update(task, completed=percentage)
                        
                        if elapsed_time >= duration_ms:
                            break
                    else:
                        # Adjust timer for pause
                        pause_start = time.time()
                        while self.is_paused and not self.skip_requested:
                            key = kb.get_key(0.1)
                            if key == ' ':
                                self.is_paused = False
                                self.audio_player.unpause()
                                progress.update(task, description="[cyan]Meditation Progress")
                            elif key == 's':
                                self.skip_requested = True
                                break
                        if not self.skip_requested:
                            pause_duration = time.time() - pause_start
                            start_time += pause_duration
            
        self.audio_player.stop()
        
        console.print()
        if self.skip_requested:
            console.print("[yellow]⏭️  Meditation skipped[/yellow]")
        else:
            console.print("[green]✨ Meditation complete![/green]")
        
        # Small delay to ensure clean transition
        time.sleep(1)


def show_notification():
    """Show desktop notification when session ends"""
    notification.notify(
        title='Focus Session Complete! 🎉',
        message='Your focus session has ended. Great work!',
        timeout=10
    )


def get_asset_path(filename):
    """Get the full path to an asset file"""
    return Path(__file__).parent / 'assets' / filename


# Removed unused function


@click.command()
def main():
    """Focus Session CLI - Enhance your productivity with mindful work sessions"""
    
    # Initialize audio player
    audio_player = AudioPlayer()
    
    # Welcome screen
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]🧘 Focus Session CLI[/bold cyan]\n\n"
        "[dim]Enhance your productivity with mindful work sessions[/dim]",
        border_style="cyan"
    ))
    console.print()
    
    # First ask about meditation
    meditation = click.confirm("Would you like to start with meditation to clear your head?", default=True)
    
    # Meditation phase
    if meditation:
        meditation_player = MeditationPlayer(
            audio_player, 
            get_asset_path('meditation.mp3')
        )
        meditation_player.play_with_progress()
        time.sleep(1)
    
    # Ask for focus duration
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]⏱️  Session Duration[/bold cyan]\n\n"
        "Choose your focus session duration:",
        border_style="cyan"
    ))
    console.print()
    
    duration = click.prompt(
        "Select duration (minutes)",
        type=click.Choice(['1', '11', '21', '31']),
        default='21',
        show_choices=True
    )
    
    # Focus session phase
    console.clear()
    console.print(Panel.fit(
        f"[bold cyan]🎯 Starting {duration}-minute Focus Session[/bold cyan]\n\n"
        "[dim]Controls:[/dim]\n"
        "  [bold]SPACE[/bold] → Pause/Resume\n"
        "  [bold]M[/bold]     → Mute/Unmute\n"
        "  [bold]Q[/bold]     → Quit session",
        border_style="cyan"
    ))
    console.print()
    
    # Start rain sound
    audio_player.play(get_asset_path('rain.mp3'), loop=True)
    
    # Create focus session
    session = FocusSession(int(duration), audio_player)
    
    # Main session loop with simple display
    try:
        from rich.live import Live
        from rich.text import Text
        
        # Create initial status text
        status_text = Text()
        
        with Live(status_text, console=console, refresh_per_second=10, transient=False) as live:
            with KeyboardInput() as kb:
                last_status_msg = ""
                
                while not session.is_complete():
                    # Check for keyboard input
                    key = kb.get_key(0.1)
                    
                    if key == ' ':
                        is_paused = session.toggle_pause()
                        if is_paused:
                            last_status_msg = "PAUSED"
                        else:
                            last_status_msg = "RESUMED"
                    elif key == 'm':
                        is_muted = audio_player.toggle_mute()
                        if is_muted:
                            last_status_msg = "MUTED"
                        else:
                            last_status_msg = "SOUND ON"
                    elif key == 'q':
                        session.session_active = False
                        break
                    
                    session.update_timer()
                    
                    # Display timer with progress
                    time_str = session.get_progress_string()
                    progress = session.get_progress_percentage()
                    filled = int(progress / 5)  # 20 blocks total
                    
                    # Build the status text
                    status_text = Text()
                    status_text.append("  ")
                    status_text.append("⏱️  ", style="bold cyan")
                    status_text.append(time_str, style="bold cyan")
                    status_text.append("  ")
                    status_text.append("█" * filled, style="cyan")
                    status_text.append("░" * (20 - filled), style="dim cyan")
                    status_text.append("  ")
                    
                    if last_status_msg:
                        if "PAUSED" in last_status_msg:
                            status_text.append("║ ⏸  PAUSED", style="yellow")
                        elif "RESUMED" in last_status_msg:
                            status_text.append("║ ▶  RESUMED", style="green")
                        elif "MUTED" in last_status_msg:
                            status_text.append("║ 🔇 MUTED", style="red")
                        elif "SOUND ON" in last_status_msg:
                            status_text.append("║ 🔊 SOUND ON", style="green")
                    else:
                        status_text.append("║ ▶  ACTIVE", style="green")
                    
                    live.update(status_text)
        
        # Session complete
        audio_player.stop()
        
        console.print()
        if session.time_remaining == 0:  # Natural completion
            console.print(Panel.fit(
                "[bold green]🎉 Session Complete![/bold green]\n\n"
                "[dim]Great work! You've completed your focus session.[/dim]",
                border_style="green"
            ))
            
            # Show notification
            show_notification()
            
            # Play notification sound in loop
            audio_player.play(get_asset_path('notification.wav'), loop=True)
            console.print("\n[dim]Press Enter to dismiss notification...[/dim]")
            input()
        else:  # User quit
            console.print(Panel.fit(
                "[yellow]👋 Session ended early[/yellow]\n\n"
                "[dim]No worries! Every moment of focus counts.[/dim]",
                border_style="yellow"
            ))
            
    finally:
        audio_player.stop()
        pygame.quit()
        console.clear()


if __name__ == '__main__':
    main()