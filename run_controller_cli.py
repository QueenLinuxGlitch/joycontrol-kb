#!/usr/bin/env python3

import argparse
import asyncio
import logging
import os
import keyboard
import time
import shelve

from aioconsole import ainput

from joycontrol import logging_default as log, utils
from joycontrol.command_line_interface import ControllerCLI
from joycontrol.controller import Controller
from joycontrol.controller_state import ControllerState, button_push, StickState
from joycontrol.memory import FlashMemory
from joycontrol.protocol import controller_protocol_factory
from joycontrol.server import create_hid_server

logger = logging.getLogger(__name__)

"""Emulates Switch controller. Opens joycontrol.command_line_interface to send button commands and more.

While running the cli, call "help" for an explanation of available commands.

Usage:
    run_controller_cli.py <controller> [--device_id | -d  <bluetooth_adapter_id>]
                                       [--spi_flash <spi_flash_memory_file>]
                                       [--reconnect_bt_addr | -r <console_bluetooth_address>]
                                       [--log | -l <communication_log_file>]
                                       [--nfc <nfc_data_file>]
    run_controller_cli.py -h | --help

Arguments:
    controller      Choose which controller to emulate. Either "JOYCON_R", "JOYCON_L" or "PRO_CONTROLLER"

Options:
    -d --device_id <bluetooth_adapter_id>   ID of the bluetooth adapter. Integer matching the digit in the hci* notation
                                            (e.g. hci0, hci1, ...) or Bluetooth mac address of the adapter in string
                                            notation (e.g. "FF:FF:FF:FF:FF:FF").
                                            Note: Selection of adapters may not work if the bluez "input" plugin is
                                            enabled.

    --spi_flash <spi_flash_memory_file>     Memory dump of a real Switch controller. Required for joystick emulation.
                                            Allows displaying of JoyCon colors.
                                            Memory dumps can be created using the dump_spi_flash.py script.

    -r --reconnect_bt_addr <console_bluetooth_address>  Previously connected Switch console Bluetooth address in string
                                                        notation (e.g. "FF:FF:FF:FF:FF:FF") for reconnection.
                                                        Does not require the "Change Grip/Order" menu to be opened,

    -l --log <communication_log_file>       Write hid communication (input reports and output reports) to a file.

    --nfc <nfc_data_file>                   Sets the nfc data of the controller to a given nfc dump upon initial
                                            connection.
"""
def keyToConBtn(key): #this method translates recorded key events to respective controller buttons pressed for recording playback
    namedKey = None
    keyBinding = {'q': 'left', 'w': 'lStickUp', 'e': 'up', 'r': 'zl', 't': 'l', 'y': 'r', 'u': 'zr', 'i': 'rStickUp', 'a': 'lStickL', 's': 'lStickDown', 'd': 'lStickR', 'f': 'right', 'g': 'capture', 'h': 'home', 'j': 'rStickL', 'k': 'rStickDown', 'l':  'rStickR', 'c': 'down', 'up': 'x', 'down': 'b', 'left': 'y', 'right': 'a', '[': 'minus', ']': 'plus'}
    testKeys = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'c', 'up', 'down', 'left', 'right', '+', '-']
    for testKey in testKeys:
        testKeyCode = keyboard.key_to_scan_codes(testKey)
        #print('testKeyCode:')
        #print(testKeyCode)
        if testKeyCode[0] == key:
            namedKey = testKey
            #print('namedKey:')
            #print(namedKey)
    if namedKey in keyBinding:
        conBtnPressed = keyBinding[namedKey]
        return conBtnPressed

def bindKeyboard(controller_state: ControllerState):#this method binds specific keys to each button on the pro controller for keyboard control
    #callbacks:
    def APress(self):
        controller_state.button_state.set_button('a')
    def AUnpress(self):
        controller_state.button_state.set_button('a', pushed=False)
    def BPress(self):
        controller_state.button_state.set_button('b')
    def BUnpress(self):
        controller_state.button_state.set_button('b', pushed=False)
    def XPress(self):
        controller_state.button_state.set_button('x')
    def XUnpress(self):
        controller_state.button_state.set_button('x', pushed=False)
    def YPress(self):
        controller_state.button_state.set_button('y')
    def YUnpress(self):
        controller_state.button_state.set_button('y', pushed=False)
    def UPPress(self):
        controller_state.button_state.set_button('up')
    def UPUnpress(self):
        controller_state.button_state.set_button('up', pushed=False)
    def DOWNPress(self):
        controller_state.button_state.set_button('down')
    def DOWNUnpress(self):
        controller_state.button_state.set_button('down', pushed=False)
    def LEFTPress(self):
        controller_state.button_state.set_button('left')
    def LEFTUnpress(self):
        controller_state.button_state.set_button('left', pushed=False)
    def RIGHTPress(self):
        controller_state.button_state.set_button('right')
    def RIGHTUnpress(self):
        controller_state.button_state.set_button('right', pushed=False)
    def PLUSPress(self):
        controller_state.button_state.set_button('plus')
    def PLUSUnpress(self):
        controller_state.button_state.set_button('plus', pushed=False)
    def MINUSPress(self):
        controller_state.button_state.set_button('minus')
    def MINUSUnpress(self):
        controller_state.button_state.set_button('minus', pushed=False)
    def HOMEPress(self):
        controller_state.button_state.set_button('home')
    def HOMEUnpress(self):
        controller_state.button_state.set_button('home', pushed=False)
    def CAPPress(self):
        controller_state.button_state.set_button('capture')
    def CAPUnpress(self):
        controller_state.button_state.set_button('capture', pushed=False)
    def LBUMPPress(self):
        controller_state.button_state.set_button('l')
    def LBUMPUnpress(self):
        controller_state.button_state.set_button('l', pushed=False)
    def RBUMPPress(self):
        controller_state.button_state.set_button('r')
    def RBUMPUnpress(self):
        controller_state.button_state.set_button('r', pushed=False)
    def ZLPress(self):
        controller_state.button_state.set_button('zl')
    def ZLUnpress(self):
        controller_state.button_state.set_button('zl', pushed=False)
    def ZRPress(self):
        controller_state.button_state.set_button('zr')
    def ZRUnpress(self):
        controller_state.button_state.set_button('zr', pushed=False)

        # Stick state handler callbacks
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state

    def UpLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'up', None)
    def DownLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'down', None)
    def LeftLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'left', None)
    def RightLStickPress(self):
        ControllerCLI._set_stick(LeftStick, 'right', None)
    def LStickUnpress(self):
        ControllerCLI._set_stick(LeftStick, 'center', None)

        #Right Stick

    def UpRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'up', None)
    def DownRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'down', None)
    def LeftRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'left', None)
    def RightRStickPress(self):
        ControllerCLI._set_stick(RightStick, 'right', None)
    def RStickUnpress(self):
        ControllerCLI._set_stick(RightStick, 'center', None)

    #key listeners
    keyboard.on_press_key('q', LEFTPress)
    keyboard.on_release_key('q', LEFTUnpress)

    keyboard.on_press_key('w', UpLStickPress)
    keyboard.on_release_key('w', LStickUnpress)

    keyboard.on_press_key('e', UPPress)
    keyboard.on_release_key('e', UPUnpress)

    keyboard.on_press_key('r', ZLPress)
    keyboard.on_release_key('r', ZLUnpress)

    keyboard.on_press_key('t', LBUMPPress)
    keyboard.on_release_key('t', LBUMPUnpress)

    keyboard.on_press_key('y', RBUMPPress)
    keyboard.on_release_key('y', RBUMPUnpress)

    keyboard.on_press_key('u', ZRPress)
    keyboard.on_release_key('u', ZRUnpress)

    keyboard.on_press_key('i', UpRStickPress)
    keyboard.on_release_key('i', RStickUnpress)

    keyboard.on_press_key('a', LeftLStickPress)
    keyboard.on_release_key('a', LStickUnpress)

    keyboard.on_press_key('s', DownLStickPress)
    keyboard.on_release_key('s', LStickUnpress)

    keyboard.on_press_key('d', RightLStickPress)
    keyboard.on_release_key('d', LStickUnpress)

    keyboard.on_press_key('f', RIGHTPress)
    keyboard.on_release_key('f', RIGHTUnpress)

    keyboard.on_press_key('g', CAPPress)
    keyboard.on_release_key('g', CAPUnpress)

    keyboard.on_press_key('h', HOMEPress)
    keyboard.on_release_key('h', HOMEUnpress)

    keyboard.on_press_key('j', LeftRStickPress)
    keyboard.on_release_key('j', RStickUnpress)

    keyboard.on_press_key('k', DownRStickPress)
    keyboard.on_release_key('k', RStickUnpress)

    keyboard.on_press_key('l', RightRStickPress)
    keyboard.on_release_key('l', RStickUnpress)

    keyboard.on_press_key('c', DOWNPress)
    keyboard.on_release_key('c', DOWNUnpress)

    keyboard.on_press_key(']', PLUSPress)
    keyboard.on_release_key(']', PLUSUnpress)

    keyboard.on_press_key('[', MINUSPress)
    keyboard.on_release_key('[', MINUSUnpress)

    keyboard.on_press_key('up', XPress)
    keyboard.on_release_key('up', XUnpress)

    keyboard.on_press_key('down', BPress)
    keyboard.on_release_key('down', BUnpress)

    keyboard.on_press_key('left', YPress)
    keyboard.on_release_key('left', YUnpress)

    keyboard.on_press_key('right', APress)
    keyboard.on_release_key('right', AUnpress)
    print(' ')
    #print('keys bound')

async def directStateSet(btnTrans, controller_state: ControllerState): #this method sets button/stick states during recording playback (button PRESS/ stick UDLR)
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    btnsList = ['x', 'y', 'b', 'a', 'plus', 'minus', 'home', 'capture', 'zl', 'zr', 'l', 'r', 'up', 'down', 'left', 'right']
    lStickList = ['lStickUp', 'lStickDown', 'lStickL', 'lStickR']
    rStickList = ['rStickUp', 'rStickDown', 'rStickL', 'rStickR']
    if btnTrans in btnsList:
        #print(btnTrans)
        controller_state.button_state.set_button(btnTrans)
        await controller_state.send()
    elif btnTrans in lStickList:
        #print(btnTrans)
        if btnTrans == 'lStickDown':
            ControllerCLI._set_stick(LeftStick, 'down', None)
            await controller_state.send()
        elif btnTrans == 'lStickUp':
            ControllerCLI._set_stick(LeftStick, 'up', None)
            await controller_state.send()
        elif btnTrans == 'lStickL':
            ControllerCLI._set_stick(LeftStick, 'left', None)
            await controller_state.send()
        elif btnTrans == 'lStickR':
            ControllerCLI._set_stick(LeftStick, 'right', None)
            await controller_state.send()
    elif btnTrans in rStickList:
        if btnTrans == 'rStickDown':
            ControllerCLI._set_stick(RightStick, 'down', None)
            await controller_state.send()
        elif btnTrans == 'rStickUp':
            ControllerCLI._set_stick(RightStick, 'up', None)
            await controller_state.send()
        elif btnTrans == 'rStickL':
            ControllerCLI._set_stick(RightStick, 'left', None)
            await controller_state.send()
        elif btnTrans == 'rStickR':
            ControllerCLI._set_stick(RightStick, 'right', None)
            await controller_state.send()

async def directStateUNSet(btnTrans, controller_state: ControllerState): #this method sets button/stick states during recording playback (button RELEASE/ stick CENTER)
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    btnsList = ['x', 'y', 'b', 'a', 'plus', 'minus', 'home', 'capture', 'zl', 'zr', 'l', 'r', 'up', 'down', 'left', 'right']
    lStickList = ['lStickUp', 'lStickDown', 'lStickL', 'lStickR']
    rStickList = ['rStickUp', 'rStickDown', 'rStickL', 'rStickR']
    if btnTrans in btnsList:
        controller_state.button_state.set_button(btnTrans, pushed=False)
        await controller_state.send()
    elif btnTrans in lStickList:
        ControllerCLI._set_stick(LeftStick, 'center', None)
        await controller_state.send()
    elif btnTrans in rStickList:
        ControllerCLI._set_stick(RightStick, 'center', None)
        await controller_state.send()

async def delete_recording(controller_state: ControllerState): #This method deletes saved recordings
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')
    # waits until controller is fully connected
    await controller_state.connect()
    savedRecordings = shelve.open('savedRecs', writeback=True)
    recList = list(savedRecordings.keys())
    print('Saved Recordings:')
    print(recList)
    print('Enter the name of the recording you want to delete')
    print('Then press <enter> to delete.')
    recordingName = await ainput(prompt='Recording name:')
    if recordingName in recList:
        del savedRecordings[recordingName]
        print('Recording deleted')
    else:
        print('Recording name not recognized')

async def recording_playback(controller_state: ControllerState): #This method replays saved recordings
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')
    # waits until controller is fully connected
    await controller_state.connect()
    savedRecordings = shelve.open('savedRecs', writeback=True)
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    recList = list(savedRecordings.keys())
    print('Saved Recordings:')
    print(recList)
    print('Enter the name of the recording you want to playback')
    print('Then press <enter> to start playback.')
    recordingName = await ainput(prompt='Recording name:')
    if recordingName in recList:
        recording = savedRecordings[recordingName]
        speed_factor = 1
        last_time = None
        for event in recording:
            if speed_factor > 0 and last_time is not None:
                time.sleep((event.time - last_time) / speed_factor)
            last_time = event.time
            key = event.scan_code or event.name
            btnTrans = keyToConBtn(key)
            await directStateSet(btnTrans, controller_state) if event.event_type == keyboard.KEY_DOWN else  await directStateUNSet(btnTrans, controller_state)
        keyboard.unhook_all()
        ControllerCLI._set_stick(RightStick, 'center', None)
        ControllerCLI._set_stick(LeftStick, 'center', None)
        await controller_state.send()
    else:
        print('Recording name not recognized')

async def record_keyboard(controller_state: ControllerState): #this method binds keyboard to conroller and records input for later playback
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')
    # waits until controller is fully connected
    await controller_state.connect()
    print('Using only letters and numbers, type a name for this recording')
    print('Then press <enter> to start recording keyboard control.')
    recordingName = await ainput(prompt='Recording name:')

    #button state handler callbacks
    savedRecordings = shelve.open('savedRecs', writeback=True)
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    bindKeyboard(controller_state)
    keyboard.start_recording()
    await ainput(prompt='Press <enter> to stop recording and exit keyboard control.')
    recording = keyboard.stop_recording()
    keyboard.unhook_all()

    savedRecordings[recordingName] = recording
    savedRecordings.close()

    ControllerCLI._set_stick(RightStick, 'center', None)
    ControllerCLI._set_stick(LeftStick, 'center', None)
    await controller_state.send()

async def keyboard_control(controller_state: ControllerState):# this method binds keyboard to controller for CLI keyboard control of switch
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')
    # waits until controller is fully connected
    await controller_state.connect()

    await ainput(prompt='Press <enter> to start keyboard control.')

    #button state handler callbacks
    LeftStick = controller_state.l_stick_state
    RightStick = controller_state.r_stick_state
    bindKeyboard(controller_state)
    await ainput(prompt='Press <enter> to exit keyboard control.')
    keyboard.unhook_all()
    ControllerCLI._set_stick(RightStick, 'center', None)
    ControllerCLI._set_stick(LeftStick, 'center', None)
    await controller_state.send()



async def test_controller_buttons(controller_state: ControllerState): #this method navigates to the "Test Controller Buttons" menu and presses all buttons.
    """
    Example controller script.
    Navigates to the "Test Controller Buttons" menu and presses all buttons.
    """
    if controller_state.get_controller() != Controller.PRO_CONTROLLER:
        raise ValueError('This script only works with the Pro Controller!')

    # waits until controller is fully connected
    await controller_state.connect()

    await ainput(prompt='Make sure the Switch is in the Home menu and press <enter> to continue.')

    """
    # We assume we are in the "Change Grip/Order" menu of the switch
    await button_push(controller_state, 'home')

    # wait for the animation
    await asyncio.sleep(1)
    """

    # Goto settings
    await button_push(controller_state, 'down', sec=1)
    await button_push(controller_state, 'right', sec=2)
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'left')
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=4)
    await asyncio.sleep(0.3)

    # goto "Controllers and Sensors" menu
    for _ in range(2):
        await button_push(controller_state, 'up')
        await asyncio.sleep(0.3)
    await button_push(controller_state, 'right')
    await asyncio.sleep(0.3)

    # go all the way down
    await button_push(controller_state, 'down', sec=3)
    await asyncio.sleep(0.3)

    # goto "Test Input Devices" menu
    await button_push(controller_state, 'up')
    await asyncio.sleep(0.3)
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # goto "Test Controller Buttons" menu
    await button_push(controller_state, 'a')
    await asyncio.sleep(0.3)

    # push all buttons except home and capture
    button_list = controller_state.button_state.get_available_buttons()
    if 'capture' in button_list:
        button_list.remove('capture')
    if 'home' in button_list:
        button_list.remove('home')

    user_input = asyncio.ensure_future(
        ainput(prompt='Pressing all buttons... Press <enter> to stop.')
    )

    # push all buttons consecutively until user input
    while not user_input.done():
        for button in button_list:
            await button_push(controller_state, button)
            await asyncio.sleep(0.1)

            if user_input.done():
                break

    # await future to trigger exceptions in case something went wrong
    await user_input

    # go back to home
    await button_push(controller_state, 'home')


async def set_nfc(controller_state, file_path):
    """
    Sets nfc content of the controller state to contents of the given file.
    :param controller_state: Emulated controller state
    :param file_path: Path to nfc dump file
    """
    loop = asyncio.get_event_loop()

    with open(file_path, 'rb') as nfc_file:
        content = await loop.run_in_executor(None, nfc_file.read)
        controller_state.set_nfc(content)


async def mash_button(controller_state, button, interval):
    # waits until controller is fully connected
    await controller_state.connect()

    if button not in controller_state.button_state.get_available_buttons():
        raise ValueError(f'Button {button} does not exist on {controller_state.get_controller()}')

    user_input = asyncio.ensure_future(
        ainput(prompt=f'Pressing the {button} button every {interval} seconds... Press <enter> to stop.')
    )
    # push a button repeatedly until user input
    while not user_input.done():
        await button_push(controller_state, button)
        await asyncio.sleep(float(interval))

    # await future to trigger exceptions in case something went wrong
    await user_input


async def _main(args):
    # parse the spi flash
    if args.spi_flash:
        with open(args.spi_flash, 'rb') as spi_flash_file:
            spi_flash = FlashMemory(spi_flash_file.read())
    else:
        # Create memory containing default controller stick calibration
        spi_flash = FlashMemory()

    # Get controller name to emulate from arguments
    controller = Controller.from_arg(args.controller)

    with utils.get_output(path=args.log, default=None) as capture_file:
        factory = controller_protocol_factory(controller, spi_flash=spi_flash)
        ctl_psm, itr_psm = 17, 19
        transport, protocol = await create_hid_server(factory, reconnect_bt_addr=args.reconnect_bt_addr,
                                                      ctl_psm=ctl_psm,
                                                      itr_psm=itr_psm, capture_file=capture_file,
                                                      device_id=args.device_id)

        controller_state = protocol.get_controller_state()

        # Create command line interface and add some extra commands
        cli = ControllerCLI(controller_state)

        # Wrap the script so we can pass the controller state. The doc string will be printed when calling 'help'
        async def _run_test_control():
            """
            test_control - test method that will be removed later
            """
            await test_control(controller_state)
        async def _run_keyboard_control():
            """
            keyboard - binds controls to keyboard. Keybinding:
            q=LEFT w=LstickUP e=UP r=ZL t=L y=R u=ZR i=RstickUP
            a=LstickLEFT s=LstickDOWN d=LstickRIGHT f=RIGHT g=capture h=home j=RstickLEFT k=RStickDOWN l=RstickRIGHT
            c=DOWN up=X down=B left=Y right=A
            plus= + minus= -
            """
            await keyboard_control(controller_state)
        async def _run_recording_control():
            """
            recording - binds controls to keyboard, and records input until recording stopped.
            saved recordings can be replayed using cmd >> recording_playback
            Keybinding:
            q=LEFT w=LstickUP e=UP r=ZL t=L y=R u=ZR i=RstickUP
            a=LstickLEFT s=LstickDOWN d=LstickRIGHT f=RIGHT g=capture h=home j=RstickLEFT k=RStickDOWN l=RstickRIGHT
            c=DOWN up=X down=B left=Y right=A
            plus= + minus= -
            """
            await record_keyboard(controller_state)

        async def _run_recording_playback():
            """
            playback - select a saved recording and replay it
            """
            await recording_playback(controller_state)

        async def _run_delete_recording():
            """
            delete_rec - select a saved recording and delete it
            """
            await delete_recording(controller_state)
        async def _run_test_controller_buttons():
            """
            test_buttons - Navigates to the "Test Controller Buttons" menu and presses all buttons.
            """
            await test_controller_buttons(controller_state)

        # Mash a button command
        async def call_mash_button(*args):
            """
            mash - Mash a specified button at a set interval
            Usage:
                mash <button> <interval>
            """
            if not len(args) == 2:
                raise ValueError('"mash_button" command requires a button and interval as arguments!')

            button, interval = args
            await mash_button(controller_state, button, interval)

        # Create nfc command
        async def nfc(*args):
            """
            nfc - Sets nfc content

            Usage:
                nfc <file_name>          Set controller state NFC content to file
                nfc remove               Remove NFC content from controller state
            """
            if controller_state.get_controller() == Controller.JOYCON_L:
                raise ValueError('NFC content cannot be set for JOYCON_L')
            elif not args:
                raise ValueError('"nfc" command requires file path to an nfc dump as argument!')
            elif args[0] == 'remove':
                controller_state.set_nfc(None)
                print('Removed nfc content.')
            else:
                await set_nfc(controller_state, args[0])

        cli.add_command('test_buttons', _run_test_controller_buttons)
        cli.add_command('keyboard', _run_keyboard_control)
        cli.add_command('recording', _run_recording_control)
        cli.add_command('playback', _run_recording_playback)
        cli.add_command('delete_rec', _run_delete_recording)
        cli.add_command('mash', call_mash_button)
        # add the script from above
        cli.add_command('nfc', nfc)


        if args.nfc is not None:
            await nfc(args.nfc)

        try:
            await cli.run()
        finally:
            logger.info('Stopping communication...')
            await transport.close()


if __name__ == '__main__':
    # check if root
    if not os.geteuid() == 0:
        raise PermissionError('Script must be run as root!')

    # setup logging
    #log.configure(console_level=logging.ERROR)
    log.configure()

    parser = argparse.ArgumentParser()
    parser.add_argument('controller', help='JOYCON_R, JOYCON_L or PRO_CONTROLLER')
    parser.add_argument('-l', '--log')
    parser.add_argument('-d', '--device_id')
    parser.add_argument('--spi_flash')
    parser.add_argument('-r', '--reconnect_bt_addr', type=str, default=None,
                        help='The Switch console Bluetooth address, for reconnecting as an already paired controller')
    parser.add_argument('--nfc', type=str, default=None)
    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        _main(args)
    )
