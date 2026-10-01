#![no_std]
#![no_main]
// One source is built by the Xtensa crate and the RISC-V crate. Each crate
// only declares its own chip features, so the other family's cfgs are expected.
#![allow(unexpected_cfgs)]
#![deny(
    clippy::mem_forget,
    reason = "mem::forget is generally not safe to do with esp_hal types, especially those \
    holding buffers for the duration of a data transfer."
)]
#![deny(clippy::large_stack_frames)]

use esp_hal::clock::CpuClock;
use esp_hal::gpio::{Level, Output, OutputConfig};
use esp_hal::main;
use esp_hal::time::{Duration, Instant};
use esp_println::println;

#[panic_handler]
fn panic(_: &core::panic::PanicInfo) -> ! {
    loop {}
}

// Default app descriptor required by the esp-idf bootloader.
esp_bootloader_esp_idf::esp_app_desc!();

#[allow(
    clippy::large_stack_frames,
    reason = "it's not unusual to allocate larger buffers etc. in main"
)]
#[main]
fn main() -> ! {
    let config = esp_hal::Config::default().with_cpu_clock(CpuClock::max());
    let peripherals = esp_hal::init(config);

    // GPIO numbers match the PlatformIO blink chip table.
    #[cfg(feature = "esp32")]
    let led_pin = peripherals.GPIO2;
    #[cfg(feature = "esp32s2")]
    let led_pin = peripherals.GPIO18;
    #[cfg(feature = "esp32s3")]
    let led_pin = peripherals.GPIO48;
    #[cfg(feature = "esp32c2")]
    let led_pin = peripherals.GPIO8;
    #[cfg(feature = "esp32c3")]
    let led_pin = peripherals.GPIO8;
    #[cfg(feature = "esp32c5")]
    let led_pin = peripherals.GPIO27;
    #[cfg(feature = "esp32c6")]
    let led_pin = peripherals.GPIO8;
    #[cfg(feature = "esp32h2")]
    let led_pin = peripherals.GPIO8;
    #[cfg(not(any(
        feature = "esp32",
        feature = "esp32s2",
        feature = "esp32s3",
        feature = "esp32c2",
        feature = "esp32c3",
        feature = "esp32c5",
        feature = "esp32c6",
        feature = "esp32h2",
    )))]
    compile_error!("enable exactly one chip feature");

    let mut led = Output::new(led_pin, Level::Low, OutputConfig::default());
    loop {
        led.set_high();
        println!("LED on");
        let on_at = Instant::now();
        while on_at.elapsed() < Duration::from_millis(500) {}
        led.set_low();
        println!("LED off");
        let off_at = Instant::now();
        while off_at.elapsed() < Duration::from_millis(500) {}
    }
}
